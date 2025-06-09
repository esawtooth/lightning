//! HTTP API layer exposing document CRUD endpoints.

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::storage::crdt::DocumentStore;

/// Shared application state containing the document store.
#[derive(Clone)]
pub struct AppState {
    pub store: Arc<Mutex<DocumentStore>>,
}

#[derive(Serialize, Deserialize)]
struct DocRequest {
    content: String,
}

#[derive(Serialize, Deserialize)]
struct DocResponse {
    id: Uuid,
    content: String,
}

pub fn router(state: Arc<Mutex<DocumentStore>>) -> Router {
    let app_state = AppState { store: state };
    Router::new()
        .route("/docs", post(create_doc))
        .route("/docs/:id", get(get_doc).put(update_doc).delete(delete_doc))
        .with_state(app_state)
}

async fn create_doc(
    State(state): State<AppState>,
    Json(req): Json<DocRequest>,
) -> Json<DocResponse> {
    let mut store = state.store.lock().await;
    let id = store.create(&req.content).expect("create");
    Json(DocResponse {
        id,
        content: req.content,
    })
}

async fn get_doc(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<DocResponse>, StatusCode> {
    let store = state.store.lock().await;
    if let Some(doc) = store.get(id) {
        Ok(Json(DocResponse {
            id,
            content: doc.text(),
        }))
    } else {
        Err(StatusCode::NOT_FOUND)
    }
}

async fn update_doc(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<DocRequest>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    let _ = store.update(id, &req.content);
    StatusCode::NO_CONTENT
}

async fn delete_doc(State(state): State<AppState>, Path(id): Path<Uuid>) -> StatusCode {
    let mut store = state.store.lock().await;
    let _ = store.delete(id);
    StatusCode::NO_CONTENT
}
