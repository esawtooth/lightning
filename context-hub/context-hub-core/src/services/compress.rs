//! Unified compress service that combines garbage collection with snapshots
//! 
//! This service performs comprehensive cleanup of all storage components
//! before creating a Git snapshot, ensuring consistent and efficient storage.

use anyhow::Result;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::{
    pointer::BlobPointerResolver,
    search::SearchIndex,
    snapshot::SnapshotManager,
    storage::{crdt::DocumentStore, metrics::StorageMetrics},
    wal::WriteAheadLog,
};

/// Configuration for the compress service
#[derive(Debug, Clone, Deserialize)]
pub struct CompressConfig {
    /// Percentage growth threshold to trigger compression (default 100%)
    #[serde(default = "default_threshold")]
    pub threshold_percent: f64,
    
    /// Minimum interval between compressions in seconds (default 300 = 5 min)
    #[serde(default = "default_min_interval")]
    pub min_interval_secs: u64,
    
    /// Maximum interval between compressions in seconds (default 86400 = 24 hours)
    #[serde(default = "default_max_interval")]
    pub max_interval_secs: u64,
    
    /// Number of snapshots to retain (default 10)
    #[serde(default = "default_retention")]
    pub snapshot_retention: usize,
    
    /// Whether to enable WAL compaction (default true)
    #[serde(default = "default_true")]
    pub enable_wal_compact: bool,
    
    /// Whether to enable blob cleanup (default true)
    #[serde(default = "default_true")]
    pub enable_blob_cleanup: bool,
    
    /// Whether to enable index optimization (default true)
    #[serde(default = "default_true")]
    pub enable_index_optimize: bool,
}

fn default_threshold() -> f64 { 100.0 }
fn default_min_interval() -> u64 { 300 }
fn default_max_interval() -> u64 { 86400 }
fn default_retention() -> usize { 10 }
fn default_true() -> bool { true }

impl Default for CompressConfig {
    fn default() -> Self {
        Self {
            threshold_percent: default_threshold(),
            min_interval_secs: default_min_interval(),
            max_interval_secs: default_max_interval(),
            snapshot_retention: default_retention(),
            enable_wal_compact: true,
            enable_blob_cleanup: true,
            enable_index_optimize: true,
        }
    }
}

/// Statistics from a compress operation
#[derive(Debug, Clone, Serialize)]
pub struct CompressStats {
    pub started_at: chrono::DateTime<Utc>,
    pub completed_at: chrono::DateTime<Utc>,
    pub duration_secs: f64,
    pub snapshot_id: String,
    pub storage_before: u64,
    pub storage_after: u64,
    pub bytes_freed: u64,
    pub documents_removed: usize,
    pub blobs_removed: usize,
    pub wal_entries_removed: usize,
    pub index_docs_removed: usize,
}

/// Unified compress service
pub struct CompressService {
    store: Arc<RwLock<DocumentStore>>,
    snapshot_manager: Arc<SnapshotManager>,
    search_index: Option<Arc<SearchIndex>>,
    wal: Option<Arc<WriteAheadLog>>,
    blob_resolver: Option<Arc<BlobPointerResolver>>,
    config: CompressConfig,
    last_compress: Arc<RwLock<Option<chrono::DateTime<Utc>>>>,
    data_dir: std::path::PathBuf,
    index_dir: std::path::PathBuf,
    wal_dir: std::path::PathBuf,
}

impl CompressService {
    pub fn new(
        store: Arc<RwLock<DocumentStore>>,
        snapshot_manager: Arc<SnapshotManager>,
        data_dir: impl AsRef<Path>,
        index_dir: impl AsRef<Path>,
        wal_dir: impl AsRef<Path>,
        config: CompressConfig,
    ) -> Self {
        Self {
            store,
            snapshot_manager,
            search_index: None,
            wal: None,
            blob_resolver: None,
            config,
            last_compress: Arc::new(RwLock::new(None)),
            data_dir: data_dir.as_ref().to_path_buf(),
            index_dir: index_dir.as_ref().to_path_buf(),
            wal_dir: wal_dir.as_ref().to_path_buf(),
        }
    }

    /// Set optional components
    pub fn with_search_index(mut self, index: Arc<SearchIndex>) -> Self {
        self.search_index = Some(index);
        self
    }

    pub fn with_wal(mut self, wal: Arc<WriteAheadLog>) -> Self {
        self.wal = Some(wal);
        self
    }

    pub fn with_blob_resolver(mut self, resolver: Arc<BlobPointerResolver>) -> Self {
        self.blob_resolver = Some(resolver);
        self
    }

    /// Check if compression should be triggered
    pub async fn should_compress(&self) -> Result<bool> {
        // Check minimum interval
        if let Some(last) = self.last_compress.read().await.as_ref() {
            let elapsed = Utc::now().signed_duration_since(*last);
            if elapsed.num_seconds() < self.config.min_interval_secs as i64 {
                return Ok(false);
            }
            
            // Force compress if max interval exceeded
            if elapsed.num_seconds() > self.config.max_interval_secs as i64 {
                return Ok(true);
            }
        }

        // Check storage growth threshold
        let blob_dir = self.blob_resolver.as_ref().map(|r| r.blob_dir());
        let metrics = StorageMetrics::calculate_current(
            &self.data_dir,
            &self.index_dir,
            blob_dir,
            &self.wal_dir,
        ).await?;
        
        Ok(metrics.should_compress(self.config.threshold_percent))
    }

    /// Perform compression: garbage collection followed by snapshot
    pub async fn compress(&self) -> Result<CompressStats> {
        let started_at = Utc::now();
        
        // Calculate initial storage
        let blob_dir = self.blob_resolver.as_ref().map(|r| r.blob_dir());
        let metrics_before = StorageMetrics::calculate_current(
            &self.data_dir,
            &self.index_dir,
            blob_dir,
            &self.wal_dir,
        ).await?;

        // Lock the store for the entire operation
        let mut store = self.store.write().await;
        
        // 1. Document garbage collection
        let (docs_removed, doc_bytes) = store.garbage_collect_documents()?;
        
        // Get active document IDs for other GC operations
        let active_ids = store.active_document_ids();
        
        // 2. WAL compaction
        let mut wal_entries_removed = 0;
        let mut wal_bytes = 0;
        if self.config.enable_wal_compact {
            if let Some(wal) = &self.wal {
                let (_, entries, bytes) = wal.compact(&active_ids).await?;
                wal_entries_removed = entries;
                wal_bytes = bytes;
            }
        }
        
        // 3. Blob cleanup
        let mut blobs_removed = 0;
        let mut blob_bytes = 0;
        if self.config.enable_blob_cleanup {
            if let Some(resolver) = &self.blob_resolver {
                let blob_refs = store.collect_blob_references();
                let (removed, bytes) = resolver.garbage_collect(&blob_refs)?;
                blobs_removed = removed;
                blob_bytes = bytes;
            }
        }
        
        // 4. Index optimization
        let mut index_docs_removed = 0;
        let mut index_bytes = 0;
        if self.config.enable_index_optimize {
            if let Some(index) = &self.search_index {
                // First clean up deleted documents
                index_docs_removed = index.cleanup_deleted(&active_ids)?;
                
                // Then optimize the index
                let (_, _, bytes) = index.optimize()?;
                index_bytes = bytes;
            }
        }
        
        // 5. Compact CRDT history
        store.compact_history()?;
        
        // 6. Create snapshot with metadata
        let total_bytes_freed = doc_bytes + wal_bytes + blob_bytes + index_bytes;
        
        // We'll create a temporary stats object for the snapshot
        let temp_stats = CompressStats {
            started_at,
            completed_at: Utc::now(),
            duration_secs: 0.0, // Will be updated later
            snapshot_id: String::new(), // Will be updated later
            storage_before: metrics_before.current_size,
            storage_after: 0, // Will be updated later
            bytes_freed: total_bytes_freed,
            documents_removed: docs_removed,
            blobs_removed,
            wal_entries_removed,
            index_docs_removed,
        };
        
        let snapshot_id = self.snapshot_manager.snapshot_with_metadata(
            &store,
            metrics_before.current_size - total_bytes_freed,
            Some(&temp_stats),
        )?;
        
        // 7. Prune old snapshots
        self.snapshot_manager.prune_old_tags(self.config.snapshot_retention)?;
        
        // Mark store as clean
        store.clear_dirty();
        
        // Update last compress time
        *self.last_compress.write().await = Some(started_at);
        
        // Calculate final storage
        let metrics_after = StorageMetrics::calculate_current(
            &self.data_dir,
            &self.index_dir,
            blob_dir,
            &self.wal_dir,
        ).await?;
        
        let completed_at = Utc::now();
        let duration_secs = completed_at
            .signed_duration_since(started_at)
            .num_milliseconds() as f64 / 1000.0;

        Ok(CompressStats {
            started_at,
            completed_at,
            duration_secs,
            snapshot_id: snapshot_id.to_string(),
            storage_before: metrics_before.current_size,
            storage_after: metrics_after.current_size,
            bytes_freed: total_bytes_freed,
            documents_removed: docs_removed,
            blobs_removed,
            wal_entries_removed,
            index_docs_removed,
        })
    }

    /// Get the last compress statistics
    pub async fn last_compress_time(&self) -> Option<chrono::DateTime<Utc>> {
        *self.last_compress.read().await
    }

    /// Get current storage metrics
    pub async fn storage_metrics(&self) -> Result<StorageMetrics> {
        let blob_dir = self.blob_resolver.as_ref().map(|r| r.blob_dir());
        StorageMetrics::calculate_current(
            &self.data_dir,
            &self.index_dir,
            blob_dir,
            &self.wal_dir,
        ).await
    }
}

/// Background task that monitors storage and triggers compression
pub async fn compress_monitor_task(
    compress_service: Arc<CompressService>,
    check_interval: std::time::Duration,
) {
    let mut interval = tokio::time::interval(check_interval);
    
    loop {
        interval.tick().await;
        
        match compress_service.should_compress().await {
            Ok(true) => {
                tracing::info!("Storage threshold exceeded, triggering compression");
                match compress_service.compress().await {
                    Ok(stats) => {
                        tracing::info!(
                            "Compression completed: {} freed in {:.2}s",
                            StorageMetrics::format_size(stats.bytes_freed),
                            stats.duration_secs
                        );
                    }
                    Err(e) => {
                        tracing::error!("Compression failed: {}", e);
                    }
                }
            }
            Ok(false) => {
                // No compression needed
            }
            Err(e) => {
                tracing::error!("Error checking compression threshold: {}", e);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_compress_config() {
        let config = CompressConfig::default();
        assert_eq!(config.threshold_percent, 100.0);
        assert_eq!(config.min_interval_secs, 300);
        assert_eq!(config.max_interval_secs, 86400);
        assert_eq!(config.snapshot_retention, 10);
    }
}