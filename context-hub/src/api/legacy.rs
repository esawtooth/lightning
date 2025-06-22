//! Legacy single-node HTTP API layer exposing document CRUD endpoints.

use context_hub_core::{
    auth::TokenVerifier,
    events::EventBus, 
    indexer::LiveIndex,
    storage::crdt::{DocumentStore, DocumentType},
};
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

/// API state for legacy single-node server
#[derive(Clone)]
pub struct ApiState {
    pub store: Arc<RwLock<DocumentStore>>,
    pub snapshot_dir: PathBuf,
    pub snapshot_retention: Option<usize>,
    pub indexer: Arc<LiveIndex>,
    pub events: EventBus,
    pub verifier: Arc<dyn TokenVerifier>,
}

/// Create the legacy API router
pub fn router(
    store: Arc<RwLock<DocumentStore>>,
    snapshot_dir: PathBuf,
    snapshot_retention: Option<usize>,
    indexer: Arc<LiveIndex>,
    events: EventBus,
    verifier: Arc<dyn TokenVerifier>,
) -> Router {
    let state = ApiState {
        store,
        snapshot_dir,
        snapshot_retention,
        indexer,
        events,
        verifier,
    };

    Router::new()
        .route("/docs", post(create_document).get(list_documents))
        .route(
            "/docs/{id}",
            get(get_document)
                .put(update_document)
                .patch(patch_document)
                .delete(delete_document),
        )
        .route("/folders/{id}", get(get_folder_contents))
        .route("/folders/{id}/guide", get(get_folder_guide))
        .route("/search", get(search))
        // .nest("/timeline", timeline_router(store.clone(), snapshot_dir.clone())) // Temporarily disabled
        .with_state(state)
}

// Request/Response types
#[derive(Deserialize)]
pub struct CreateDocumentRequest {
    pub name: String,
    pub content: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: Option<String>,
}

#[derive(Serialize)]
pub struct DocumentResponse {
    pub id: Uuid,
    pub name: String,
    pub content: String,
    pub owner: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: String,
    pub created_at: String,
    pub updated_at: String,
    pub index_guide: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub numbered_content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line_count: Option<usize>,
}

#[derive(Deserialize)]
pub struct UpdateDocumentRequest {
    pub content: String,
}

#[derive(Deserialize)]
pub struct PatchDocumentRequest {
    pub patch: String,
}

#[derive(Deserialize)]
pub struct SearchQuery {
    pub q: String,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
}

#[derive(Deserialize)]
pub struct DocumentQuery {
    pub format: Option<String>,
}

#[derive(Serialize)]
pub struct SearchResult {
    pub documents: Vec<DocumentSummary>,
    pub total: usize,
}

#[derive(Serialize)]
pub struct DocumentSummary {
    pub id: Uuid,
    pub name: String,
    pub snippet: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: String,
    pub updated_at: String,
    pub index_guide: Option<String>,
}

// Utility functions for line numbering and patch handling

/// Add line numbers to content
fn add_line_numbers(content: &str) -> String {
    content
        .lines()
        .enumerate()
        .map(|(i, line)| format!("{}: {}", i + 1, line))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Apply a unified diff patch to content
fn apply_patch(original: &str, patch: &str) -> Result<String, String> {
    // Simple patch application - in a production system you'd want a proper diff library
    // For now, we'll implement basic unified diff parsing
    
    let lines: Vec<&str> = original.lines().collect();
    let mut result_lines = Vec::new();
    let mut current_line = 0;
    
    // Parse the patch
    let patch_lines: Vec<&str> = patch.lines().collect();
    let mut i = 0;
    
    // Skip header lines until we find a hunk
    while i < patch_lines.len() {
        if patch_lines[i].starts_with("@@") {
            break;
        }
        i += 1;
    }
    
    if i >= patch_lines.len() {
        return Err("No valid hunk found in patch".to_string());
    }
    
    // Parse hunk header: @@ -start,count +start,count @@
    let hunk_line = patch_lines[i];
    let parts: Vec<&str> = hunk_line.split_whitespace().collect();
    if parts.len() < 3 {
        return Err("Invalid hunk header".to_string());
    }
    
    let old_start = parts[1].trim_start_matches('-').split(',').next()
        .and_then(|s| s.parse::<usize>().ok())
        .ok_or("Invalid old start line")?;
    
    // Convert to 0-based indexing
    let old_start = old_start.saturating_sub(1);
    
    // Copy lines before the hunk
    result_lines.extend_from_slice(&lines[current_line..old_start.min(lines.len())]);
    current_line = old_start;
    
    // Process hunk lines
    i += 1;
    while i < patch_lines.len() && !patch_lines[i].starts_with("@@") {
        let line = patch_lines[i];
        if line.starts_with(' ') || line.starts_with('\\') {
            // Context line - copy from original
            if current_line < lines.len() {
                result_lines.push(lines[current_line]);
                current_line += 1;
            }
        } else if line.starts_with('-') {
            // Deleted line - skip in original
            current_line += 1;
        } else if line.starts_with('+') {
            // Added line - add to result
            result_lines.push(&line[1..]);
        }
        i += 1;
    }
    
    // Copy remaining lines
    if current_line < lines.len() {
        result_lines.extend_from_slice(&lines[current_line..]);
    }
    
    Ok(result_lines.join("\n"))
}

// Helper to collect index guides from root to current folder
async fn collect_index_guides(
    store: &DocumentStore,
    folder_id: Option<Uuid>,
) -> String {
    let mut guides = Vec::new();
    let mut current_folder = folder_id;
    
    // Walk up the folder hierarchy collecting index guides
    while let Some(folder_id) = current_folder {
        if let Some(folder_doc) = store.get(folder_id) {
            // Look for index guide in this folder
            for (_id, doc) in store.iter() {
                if doc.parent_folder_id() == Some(folder_id) 
                    && doc.doc_type() == DocumentType::IndexGuide {
                    guides.push(doc.text());
                    break;
                }
            }
            current_folder = folder_doc.parent_folder_id();
        } else {
            break;
        }
    }
    
    // Look for root index guide
    for (_id, doc) in store.iter() {
        if doc.parent_folder_id().is_none() 
            && doc.doc_type() == DocumentType::IndexGuide {
            guides.push(doc.text());
            break;
        }
    }
    
    // Reverse to get root-to-leaf order
    guides.reverse();
    
    if guides.is_empty() {
        String::new()
    } else {
        guides.join("\n\n---\n\n")
    }
}

// Handlers
async fn create_document(
    State(state): State<ApiState>,
    Json(req): Json<CreateDocumentRequest>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let doc_type = req.doc_type
        .as_deref()
        .map(DocumentType::from_str)
        .unwrap_or(DocumentType::Text);
    
    let mut store = state.store.write().await;
    
    // Use create_folder for Folder type to ensure Index Guide is created
    let doc_id = if doc_type == DocumentType::Folder {
        // For folders, we need a parent folder ID
        let parent_id = if let Some(pid) = req.parent_folder_id {
            pid
        } else {
            store.ensure_root("default_user")
                .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        };
        
        store
            .create_folder(parent_id, req.name.clone(), "default_user".to_string())
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    } else {
        // For regular documents, use create
        store
            .create(
                req.name.clone(),
                &req.content,
                "default_user".to_string(),
                req.parent_folder_id,
                doc_type,
            )
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    };
    
    let doc = store
        .get(doc_id)
        .ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;
    
    let index_guide = collect_index_guides(&*store, req.parent_folder_id).await;
    
    let response = DocumentResponse {
        id: doc_id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: "default_user".to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
        index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
        numbered_content: None,
        line_count: None,
    };
    
    // Schedule indexing
    drop(store);
    state.indexer.schedule_update(doc_id).await;
    
    Ok(Json(response))
}

async fn get_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
    Query(query): Query<DocumentQuery>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let store = state.store.read().await;
    let doc = store.get(id).ok_or(StatusCode::NOT_FOUND)?;
    
    let index_guide = collect_index_guides(&*store, doc.parent_folder_id()).await;
    let content = doc.text();
    
    // Check if numbered format is requested
    let (numbered_content, line_count) = if query.format.as_deref() == Some("numbered") {
        let numbered = add_line_numbers(&content);
        let count = content.lines().count();
        (Some(numbered), Some(count))
    } else {
        (None, None)
    };
    
    Ok(Json(DocumentResponse {
        id,
        name: doc.name().to_string(),
        content,
        owner: "default_user".to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
        index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
        numbered_content,
        line_count,
    }))
}

async fn update_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateDocumentRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    if store.update(id, &req.content).is_ok() {
        drop(store);
        state.indexer.schedule_update(id).await;
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn patch_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
    Json(req): Json<PatchDocumentRequest>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let mut store = state.store.write().await;
    let doc = store.get(id).ok_or(StatusCode::NOT_FOUND)?;
    
    // Apply the patch
    let original_content = doc.text();
    let new_content = apply_patch(&original_content, &req.patch)
        .map_err(|_| StatusCode::BAD_REQUEST)?;
    
    // Update the document
    if store.update(id, &new_content).is_err() {
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }
    
    // Get the updated document
    let updated_doc = store.get(id).ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;
    let index_guide = collect_index_guides(&*store, updated_doc.parent_folder_id()).await;
    
    let response = DocumentResponse {
        id,
        name: updated_doc.name().to_string(),
        content: updated_doc.text(),
        owner: "default_user".to_string(),
        parent_folder_id: updated_doc.parent_folder_id(),
        doc_type: updated_doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
        index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
        numbered_content: None,
        line_count: None,
    };
    
    // Schedule indexing
    drop(store);
    state.indexer.schedule_update(id).await;
    
    Ok(Json(response))
}

async fn delete_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
) -> StatusCode {
    let mut store = state.store.write().await;
    if store.delete(id).is_ok() {
        drop(store);
        state.indexer.schedule_update(id).await;
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn list_documents(
    State(state): State<ApiState>,
) -> Result<Json<Vec<DocumentSummary>>, StatusCode> {
    let store = state.store.read().await;
    let mut documents = Vec::new();
    
    // Collect all documents
    for (id, doc) in store.iter() {
        
        let snippet = if doc.text().len() > 100 {
            format!("{}...", &doc.text()[..100])
        } else {
            doc.text()
        };
        
        // Collect index guides for this document's location
        let index_guide = collect_index_guides(&*store, doc.parent_folder_id()).await;
        
        documents.push(DocumentSummary {
            id: *id,
            name: doc.name().to_string(),
            snippet,
            parent_folder_id: doc.parent_folder_id(),
            doc_type: doc.doc_type().as_str().to_string(),
            updated_at: chrono::Utc::now().to_rfc3339(),
            index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
        });
    }
    
    Ok(Json(documents))
}

async fn search(
    State(state): State<ApiState>,
    Query(params): Query<SearchQuery>,
) -> Result<Json<Vec<DocumentSummary>>, StatusCode> {
    let limit = params.limit.unwrap_or(10);
    
    let doc_ids = state.indexer
        .search(&params.q, limit)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    
    let store = state.store.read().await;
    let mut documents = Vec::new();
    
    for doc_id in &doc_ids {
        if let Some(doc) = store.get(*doc_id) {
            let snippet = if doc.text().len() > 100 {
                format!("{}...", &doc.text()[..100])
            } else {
                doc.text()
            };
            
            // Collect index guides for this document's location
            let index_guide = collect_index_guides(&*store, doc.parent_folder_id()).await;
            
            documents.push(DocumentSummary {
                id: *doc_id,
                name: doc.name().to_string(),
                snippet,
                parent_folder_id: doc.parent_folder_id(),
                doc_type: doc.doc_type().as_str().to_string(),
                updated_at: chrono::Utc::now().to_rfc3339(),
                index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
            });
        }
    }
    
    Ok(Json(documents))
}

async fn get_folder_contents(
    State(state): State<ApiState>,
    Path(folder_id): Path<Uuid>,
) -> Result<Json<Vec<DocumentSummary>>, StatusCode> {
    let store = state.store.read().await;
    
    // Verify the folder exists and is a folder
    let folder = store.get(folder_id).ok_or(StatusCode::NOT_FOUND)?;
    if folder.doc_type() != DocumentType::Folder {
        return Err(StatusCode::BAD_REQUEST);
    }
    
    // Collect index guides for this folder
    let folder_index_guide = collect_index_guides(&*store, Some(folder_id)).await;
    
    let mut documents = Vec::new();
    
    // Collect all documents in this folder
    for (id, doc) in store.iter() {
        // Skip index guides themselves from the listing
        if doc.doc_type() == DocumentType::IndexGuide {
            continue;
        }
        
        // Only include documents that are direct children of this folder
        if doc.parent_folder_id() == Some(folder_id) {
            let snippet = if doc.text().len() > 100 {
                format!("{}...", &doc.text()[..100])
            } else {
                doc.text()
            };
            
            documents.push(DocumentSummary {
                id: *id,
                name: doc.name().to_string(),
                snippet,
                parent_folder_id: doc.parent_folder_id(),
                doc_type: doc.doc_type().as_str().to_string(),
                updated_at: chrono::Utc::now().to_rfc3339(),
                index_guide: if !folder_index_guide.is_empty() { Some(folder_index_guide.clone()) } else { None },
            });
        }
    }
    
    Ok(Json(documents))
}

#[derive(Serialize)]
pub struct FolderGuideResponse {
    pub content: String,
}

async fn get_folder_guide(
    State(state): State<ApiState>,
    Path(folder_id): Path<Uuid>,
) -> Result<Json<FolderGuideResponse>, StatusCode> {
    let store = state.store.read().await;
    
    // Verify the folder exists and is a folder
    let folder = store.get(folder_id).ok_or(StatusCode::NOT_FOUND)?;
    if folder.doc_type() != DocumentType::Folder {
        return Err(StatusCode::BAD_REQUEST);
    }
    
    // Collect index guides for this folder
    let guide_content = collect_index_guides(&*store, Some(folder_id)).await;
    
    Ok(Json(FolderGuideResponse {
        content: guide_content,
    }))
}

// Timeline router factory - temporarily disabled
// fn timeline_router(store: Arc<RwLock<DocumentStore>>, snapshot_dir: PathBuf) -> Router {
//     // Implementation temporarily disabled due to Send/Sync issues with SnapshotManager
//     Router::new()
// }