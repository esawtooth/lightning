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
                .delete(delete_document),
        )
        .route("/folders/{id}", get(get_folder_contents))
        .route("/folders/{id}/guide", get(get_folder_guide))
        .route("/search", get(search))
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
}

#[derive(Deserialize)]
pub struct UpdateDocumentRequest {
    pub content: String,
}

#[derive(Deserialize)]
pub struct SearchQuery {
    pub q: String,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
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
    pub doc_type: String,
    pub updated_at: String,
    pub index_guide: Option<String>,
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
    let doc_id = store
        .create(
            req.name.clone(),
            &req.content,
            "default_user".to_string(),
            req.parent_folder_id,
            doc_type,
        )
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    
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
    };
    
    // Schedule indexing
    drop(store);
    state.indexer.schedule_update(doc_id).await;
    
    Ok(Json(response))
}

async fn get_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let store = state.store.read().await;
    let doc = store.get(id).ok_or(StatusCode::NOT_FOUND)?;
    
    let index_guide = collect_index_guides(&*store, doc.parent_folder_id()).await;
    
    Ok(Json(DocumentResponse {
        id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: "default_user".to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
        index_guide: if !index_guide.is_empty() { Some(index_guide) } else { None },
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
        // Skip index guides themselves from the listing
        if doc.doc_type() == DocumentType::IndexGuide {
            continue;
        }
        
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