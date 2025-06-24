use std::path::{Path, PathBuf};
use notify::{DebouncedEvent, RecommendedWatcher, Watcher};
use crate::storage::crdt::{Document, DocumentType};
use crate::pointer::{Pointer, PointerResolver};
use tokio::sync::mpsc;
use std::collections::HashMap;

/// Handles bidirectional sync between filesystem and Context Hub
pub struct BidirectionalSync {
    storage: Arc<dyn Storage>,
    mount_point: PathBuf,
    /// Maps filesystem paths to document IDs
    path_map: Arc<RwLock<BiMap<PathBuf, String>>>,
    /// File watcher
    watcher: RecommendedWatcher,
    /// Channel for filesystem events
    event_tx: mpsc::Sender<FilesystemEvent>,
}

#[derive(Debug)]
pub enum FilesystemEvent {
    Created(PathBuf),
    Modified(PathBuf),
    Deleted(PathBuf),
    Renamed { from: PathBuf, to: PathBuf },
}

impl BidirectionalSync {
    pub async fn new(
        storage: Arc<dyn Storage>,
        mount_point: PathBuf,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let (event_tx, mut event_rx) = mpsc::channel(1000);
        let path_map = Arc::new(RwLock::new(BiMap::new()));
        
        // Create file watcher
        let (tx, rx) = std::sync::mpsc::channel();
        let watcher = Watcher::new(tx, Duration::from_millis(500))?;
        
        // Process filesystem events
        let storage_clone = storage.clone();
        let path_map_clone = path_map.clone();
        let event_tx_clone = event_tx.clone();
        
        tokio::spawn(async move {
            while let Ok(event) = rx.recv() {
                if let Err(e) = Self::handle_notify_event(
                    event,
                    &event_tx_clone,
                ).await {
                    eprintln!("Error handling filesystem event: {}", e);
                }
            }
        });
        
        // Process sync events
        let storage_clone2 = storage.clone();
        let path_map_clone2 = path_map.clone();
        
        tokio::spawn(async move {
            while let Some(event) = event_rx.recv().await {
                if let Err(e) = Self::sync_filesystem_event(
                    event,
                    &storage_clone2,
                    &path_map_clone2,
                ).await {
                    eprintln!("Error syncing filesystem event: {}", e);
                }
            }
        });
        
        // Watch the mount point
        watcher.watch(&mount_point, notify::RecursiveMode::Recursive)?;
        
        Ok(Self {
            storage,
            mount_point,
            path_map,
            watcher,
            event_tx,
        })
    }
    
    /// Sync a filesystem event to Context Hub using CRDTs
    async fn sync_filesystem_event(
        event: FilesystemEvent,
        storage: &Arc<dyn Storage>,
        path_map: &Arc<RwLock<BiMap<PathBuf, String>>>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        match event {
            FilesystemEvent::Created(path) => {
                // Check if it's a file or directory
                let metadata = tokio::fs::metadata(&path).await?;
                
                if metadata.is_file() {
                    // Read file content
                    let content = tokio::fs::read_to_string(&path).await?;
                    
                    // Create new document
                    let doc = Document {
                        id: generate_document_id(),
                        name: path.file_name()
                            .unwrap()
                            .to_string_lossy()
                            .to_string(),
                        document_type: DocumentType::Text(content),
                        parent_id: Self::find_parent_id(&path, path_map).await,
                        created_at: chrono::Utc::now().timestamp(),
                        updated_at: chrono::Utc::now().timestamp(),
                        acl: vec![],
                        external_ids: HashMap::new(),
                    };
                    
                    // Save to storage
                    storage.create_document(doc.clone()).await?;
                    
                    // Update path mapping
                    path_map.write().await.insert(path, doc.id);
                    
                } else if metadata.is_dir() {
                    // Create folder document
                    let doc = Document {
                        id: generate_document_id(),
                        name: path.file_name()
                            .unwrap()
                            .to_string_lossy()
                            .to_string(),
                        document_type: DocumentType::Folder,
                        parent_id: Self::find_parent_id(&path, path_map).await,
                        created_at: chrono::Utc::now().timestamp(),
                        updated_at: chrono::Utc::now().timestamp(),
                        acl: vec![],
                        external_ids: HashMap::new(),
                    };
                    
                    storage.create_document(doc.clone()).await?;
                    path_map.write().await.insert(path, doc.id);
                }
            }
            
            FilesystemEvent::Modified(path) => {
                if let Some(doc_id) = path_map.read().await.get_by_left(&path).cloned() {
                    if let Ok(mut doc) = storage.get_document(&doc_id).await {
                        // Update document content
                        if path.is_file() {
                            let content = tokio::fs::read_to_string(&path).await?;
                            doc.document_type = DocumentType::Text(content);
                            doc.updated_at = chrono::Utc::now().timestamp();
                            
                            // Use CRDT update to handle concurrent modifications
                            storage.update_document_crdt(doc).await?;
                        }
                    }
                }
            }
            
            FilesystemEvent::Deleted(path) => {
                if let Some(doc_id) = path_map.write().await.remove_by_left(&path) {
                    // Mark as deleted in CRDT (tombstone)
                    storage.delete_document(&doc_id).await?;
                }
            }
            
            FilesystemEvent::Renamed { from, to } => {
                if let Some(doc_id) = path_map.write().await.remove_by_left(&from) {
                    // Update document name and path mapping
                    if let Ok(mut doc) = storage.get_document(&doc_id).await {
                        doc.name = to.file_name()
                            .unwrap()
                            .to_string_lossy()
                            .to_string();
                        doc.parent_id = Self::find_parent_id(&to, path_map).await;
                        doc.updated_at = chrono::Utc::now().timestamp();
                        
                        storage.update_document_crdt(doc).await?;
                        path_map.write().await.insert(to, doc_id);
                    }
                }
            }
        }
        
        Ok(())
    }
    
    /// Sync changes from Context Hub to filesystem
    pub async fn sync_from_context_hub(&self) -> Result<(), Box<dyn std::error::Error>> {
        // Subscribe to Context Hub change events
        let mut change_stream = self.storage.subscribe_changes().await?;
        
        while let Some(change) = change_stream.recv().await {
            match change {
                StorageEvent::DocumentCreated(doc) => {
                    self.create_filesystem_entry(&doc).await?;
                }
                StorageEvent::DocumentUpdated(doc) => {
                    self.update_filesystem_entry(&doc).await?;
                }
                StorageEvent::DocumentDeleted(doc_id) => {
                    self.delete_filesystem_entry(&doc_id).await?;
                }
            }
        }
        
        Ok(())
    }
    
    async fn create_filesystem_entry(&self, doc: &Document) -> Result<(), Box<dyn std::error::Error>> {
        let path = self.document_to_path(doc).await?;
        
        // Temporarily disable watcher to avoid feedback loop
        self.pause_watching().await;
        
        match &doc.document_type {
            DocumentType::Text(content) => {
                // Create parent directories if needed
                if let Some(parent) = path.parent() {
                    tokio::fs::create_dir_all(parent).await?;
                }
                
                // Write file
                tokio::fs::write(&path, content).await?;
            }
            DocumentType::Folder => {
                tokio::fs::create_dir_all(&path).await?;
            }
            DocumentType::IndexGuide => {
                // Skip index guides in filesystem
            }
        }
        
        // Update path mapping
        self.path_map.write().await.insert(path, doc.id.clone());
        
        // Re-enable watcher
        self.resume_watching().await;
        
        Ok(())
    }
    
    /// Handle conflicts using CRDT merge
    async fn handle_conflict(
        &self,
        local_path: &Path,
        remote_doc: &Document,
    ) -> Result<(), Box<dyn std::error::Error>> {
        // Read local content
        let local_content = tokio::fs::read_to_string(local_path).await?;
        
        // Get CRDT state from storage
        let crdt_state = self.storage.get_crdt_state(&remote_doc.id).await?;
        
        // Merge using CRDT
        let merged_content = crdt_state.merge_text(&local_content)?;
        
        // Write merged content
        tokio::fs::write(local_path, &merged_content).await?;
        
        // Update document in storage
        let mut doc = remote_doc.clone();
        doc.document_type = DocumentType::Text(merged_content);
        self.storage.update_document_crdt(doc).await?;
        
        Ok(())
    }
}