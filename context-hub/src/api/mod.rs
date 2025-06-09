//! HTTP API layer exposing document CRUD endpoints.

use axum::{
    extract::{FromRequestParts, Path, State},
    http::{request::Parts, StatusCode},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::storage::crdt::{DocumentStore, DocumentType};

/// Authentication context extracted from request headers.
#[derive(Clone, Debug)]
pub struct AuthContext {
    pub user_id: String,
    pub agent_id: Option<String>,
}

impl<S> FromRequestParts<S> for AuthContext
where
    S: Send + Sync,
{
    type Rejection = StatusCode;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let headers = &parts.headers;
        let user = headers
            .get("X-User-Id")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string());
        if let Some(user_id) = user {
            let agent_id = headers
                .get("X-Agent-Id")
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string());
            Ok(Self { user_id, agent_id })
        } else {
            Err(StatusCode::UNAUTHORIZED)
        }
    }
}

/// Shared application state containing the document store.
#[derive(Clone)]
pub struct AppState {
    pub store: Arc<Mutex<DocumentStore>>,
}

#[derive(Serialize, Deserialize)]
struct DocRequest {
    name: String,
    content: String,
    parent_folder_id: Option<Uuid>,
    doc_type: Option<DocumentType>,
}

#[derive(Serialize, Deserialize)]
struct DocResponse {
    id: Uuid,
    name: String,
    content: String,
    parent_folder_id: Option<Uuid>,
    doc_type: DocumentType,
    owner: String,
}

pub fn router(state: Arc<Mutex<DocumentStore>>) -> Router {
    let app_state = AppState { store: state };
    Router::new()
        .route("/docs", post(create_doc))
        .route(
            "/docs/{id}",
            get(get_doc).put(update_doc).delete(delete_doc),
        )
        .with_state(app_state)
}

async fn create_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Json(req): Json<DocRequest>,
) -> Json<DocResponse> {
    let mut store = state.store.lock().await;
    let doc_type = req.doc_type.unwrap_or(DocumentType::Text);
    let id = store
        .create(
            req.name.clone(),
            &req.content,
            auth.user_id.clone(),
            req.parent_folder_id,
            doc_type,
        )
        .expect("create");
    Json(DocResponse {
        id,
        name: req.name,
        content: req.content,
        parent_folder_id: req.parent_folder_id,
        doc_type,
        owner: auth.user_id,
    })
}

async fn get_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<DocResponse>, StatusCode> {
    let store = state.store.lock().await;
    match store.get(id) {
        Some(doc) if doc.owner() == auth.user_id => Ok(Json(DocResponse {
            id,
            name: doc.name().to_string(),
            content: doc.text(),
            parent_folder_id: doc.parent_folder_id(),
            doc_type: doc.doc_type(),
            owner: doc.owner().to_string(),
        })),
        Some(_) => Err(StatusCode::FORBIDDEN),
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn update_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<DocRequest>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    let allowed = match store.get(id) {
        Some(doc) if doc.owner() == auth.user_id => true,
        Some(_) => return StatusCode::FORBIDDEN,
        None => return StatusCode::NOT_FOUND,
    };
    if allowed {
        let _ = store.update(id, &req.content);
        StatusCode::NO_CONTENT
    } else {
        StatusCode::FORBIDDEN
    }
}

async fn delete_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    match store.get(id) {
        Some(doc) if doc.owner() == auth.user_id => {
            let _ = store.delete(id);
            StatusCode::NO_CONTENT
        }
        Some(_) => StatusCode::FORBIDDEN,
        None => StatusCode::NOT_FOUND,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{self, Body},
        http::Request,
    };
    use serde_json::json;
    use tower::util::ServiceExt;

    #[tokio::test]
    async fn crud_endpoints() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = DocumentStore::new(tempdir.path()).unwrap();
        let app = router(Arc::new(Mutex::new(store)));

        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({"name": "file.txt", "content": "hello"}).to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let id = v["id"].as_str().unwrap();

        let req = Request::builder()
            .uri(format!("/docs/{}", id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let req = Request::builder()
            .method("PUT")
            .uri(format!("/docs/{}", id))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({"name": "file.txt", "content": "world"}).to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);

        let req = Request::builder()
            .method("DELETE")
            .uri(format!("/docs/{}", id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);
    }
}
