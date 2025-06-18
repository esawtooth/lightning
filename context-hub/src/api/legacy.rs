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
    routing::{delete, get, post, put},
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
        .route("/documents", post(create_document).get(list_documents))
        .route(
            "/documents/:id",
            get(get_document)
                .put(update_document)
                .delete(delete_document),
        )
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
    
    Ok(Json(DocumentResponse {
        id: doc_id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: "default_user".to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
    }))
}

async fn get_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let store = state.store.read().await;
    let doc = store.get(id).ok_or(StatusCode::NOT_FOUND)?;
    
    Ok(Json(DocumentResponse {
        id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: "default_user".to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
    }))
}

async fn update_document(
    State(state): State<ApiState>,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateDocumentRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    if store.update(id, &req.content).is_ok() {
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
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn list_documents(
    State(_state): State<ApiState>,
) -> Result<Json<Vec<DocumentSummary>>, StatusCode> {
    // Placeholder implementation
    Ok(Json(vec![]))
}

async fn search(
    State(_state): State<ApiState>,
    Query(_params): Query<SearchQuery>,
) -> Result<Json<SearchResult>, StatusCode> {
    // Placeholder implementation
    Ok(Json(SearchResult {
        documents: vec![],
        total: 0,
    }))
}