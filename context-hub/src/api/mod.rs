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

use crate::snapshot::SnapshotManager;
use crate::storage::crdt::{AccessLevel, DocumentStore, DocumentType};
use std::path::PathBuf;

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
    pub snapshot_dir: PathBuf,
}

#[derive(Serialize, Deserialize)]
struct DocRequest {
    name: String,
    content: String,
    parent_folder_id: Option<Uuid>,
    doc_type: Option<DocumentType>,
}

#[derive(Serialize, Deserialize)]
struct FolderCreateRequest {
    name: String,
    #[serde(default)]
    content: String,
    #[serde(rename = "type")]
    item_type: String,
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

#[derive(Serialize, Deserialize)]
struct FolderItem {
    id: Uuid,
    name: String,
    doc_type: DocumentType,
}

#[derive(Serialize, Deserialize)]
struct ShareRequest {
    user: String,
    rights: String,
}

#[derive(Serialize, Deserialize)]
struct UnshareRequest {
    user: String,
}

pub fn router(state: Arc<Mutex<DocumentStore>>, snapshot_dir: PathBuf) -> Router {
    let app_state = AppState {
        store: state,
        snapshot_dir,
    };
    Router::new()
        .route("/docs", post(create_doc))
        .route(
            "/docs/{id}",
            get(get_doc).put(update_doc).delete(delete_doc),
        )
        .route("/folders/{id}", get(list_folder).post(create_in_folder))
        .route("/folders/{id}/guide", get(get_index_guide))
        .route(
            "/folders/{id}/share",
            post(share_folder).delete(unshare_folder),
        )
        .route("/snapshot", post(snapshot_now))
        .with_state(app_state)
}

async fn create_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Json(req): Json<DocRequest>,
) -> Result<Json<DocResponse>, StatusCode> {
    let mut store = state.store.lock().await;
    let root = store.ensure_root(&auth.user_id).unwrap();
    let parent = req.parent_folder_id.unwrap_or(root);

    if !store.has_permission(
        parent,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Write,
    ) {
        return Err(StatusCode::FORBIDDEN);
    }

    let doc_type = req.doc_type.unwrap_or(DocumentType::Text);
    let id = if doc_type == DocumentType::Folder {
        store
            .create_folder(parent, req.name.clone(), auth.user_id.clone())
            .expect("create_folder")
    } else {
        store
            .create(
                req.name.clone(),
                &req.content,
                auth.user_id.clone(),
                Some(parent),
                doc_type,
            )
            .expect("create")
    };
    Ok(Json(DocResponse {
        id,
        name: req.name,
        content: req.content,
        parent_folder_id: Some(parent),
        doc_type,
        owner: auth.user_id,
    }))
}

async fn get_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<DocResponse>, StatusCode> {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(doc) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Read,
            ) {
                Ok(Json(DocResponse {
                    id,
                    name: doc.name().to_string(),
                    content: doc.text(),
                    parent_folder_id: doc.parent_folder_id(),
                    doc_type: doc.doc_type(),
                    owner: doc.owner().to_string(),
                }))
            } else {
                Err(StatusCode::FORBIDDEN)
            }
        }
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
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(_) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                let _ = store.update(id, &req.content);
                StatusCode::NO_CONTENT
            } else {
                StatusCode::FORBIDDEN
            }
        }
        None => StatusCode::NOT_FOUND,
    }
}

async fn delete_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(_) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                let _ = store.delete(id);
                StatusCode::NO_CONTENT
            } else {
                StatusCode::FORBIDDEN
            }
        }
        None => StatusCode::NOT_FOUND,
    }
}

async fn create_in_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(folder_id): Path<Uuid>,
    Json(req): Json<FolderCreateRequest>,
) -> Result<Json<DocResponse>, StatusCode> {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(folder_id) {
        Some(folder) if folder.doc_type() == DocumentType::Folder => {
            if !store.has_permission(
                folder_id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                return Err(StatusCode::FORBIDDEN);
            }
            if req.item_type.to_lowercase() == "folder" {
                let id = store
                    .create_folder(folder_id, req.name.clone(), auth.user_id.clone())
                    .expect("create_folder");
                Ok(Json(DocResponse {
                    id,
                    name: req.name,
                    content: String::new(),
                    parent_folder_id: Some(folder_id),
                    doc_type: DocumentType::Folder,
                    owner: auth.user_id,
                }))
            } else {
                let content = req.content;
                let id = store
                    .create(
                        req.name.clone(),
                        &content,
                        auth.user_id.clone(),
                        Some(folder_id),
                        DocumentType::Text,
                    )
                    .expect("create");
                Ok(Json(DocResponse {
                    id,
                    name: req.name,
                    content,
                    parent_folder_id: Some(folder_id),
                    doc_type: DocumentType::Text,
                    owner: auth.user_id,
                }))
            }
        }
        Some(_) => Err(StatusCode::BAD_REQUEST),
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn list_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<Vec<FolderItem>>, StatusCode> {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(doc) if doc.doc_type() == DocumentType::Folder => {
            if !store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Read,
            ) {
                return Err(StatusCode::FORBIDDEN);
            }
            let items = doc
                .children()
                .into_iter()
                .map(|(cid, name, typ)| FolderItem {
                    id: cid,
                    name,
                    doc_type: typ,
                })
                .collect();
            Ok(Json(items))
        }
        Some(_) => Err(StatusCode::BAD_REQUEST),
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn get_index_guide(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<DocResponse>, StatusCode> {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(folder) if folder.doc_type() == DocumentType::Folder => {
            if !store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Read,
            ) {
                return Err(StatusCode::FORBIDDEN);
            }
            if let Some(guide_id) = store.index_guide_id(id) {
                if let Some(guide) = store.get(guide_id) {
                    return Ok(Json(DocResponse {
                        id: guide_id,
                        name: guide.name().to_string(),
                        content: guide.text(),
                        parent_folder_id: guide.parent_folder_id(),
                        doc_type: guide.doc_type(),
                        owner: guide.owner().to_string(),
                    }));
                }
            }
            Err(StatusCode::NOT_FOUND)
        }
        Some(_) => Err(StatusCode::BAD_REQUEST),
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn share_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<ShareRequest>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Write,
    ) {
        return StatusCode::FORBIDDEN;
    }
    let level = if req.rights.to_lowercase() == "read" {
        AccessLevel::Read
    } else {
        AccessLevel::Write
    };
    let _ = store.add_acl(id, req.user, level);
    StatusCode::NO_CONTENT
}

async fn unshare_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<UnshareRequest>,
) -> StatusCode {
    let mut store = state.store.lock().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Write,
    ) {
        return StatusCode::FORBIDDEN;
    }
    let _ = store.remove_acl(id, &req.user);
    StatusCode::NO_CONTENT
}

async fn snapshot_now(State(state): State<AppState>, _auth: AuthContext) -> StatusCode {
    let mut store = state.store.lock().await;
    let mgr = match SnapshotManager::new(&state.snapshot_dir) {
        Ok(m) => m,
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR,
    };
    match mgr.snapshot(&store) {
        Ok(_) => {
            store.clear_dirty();
            StatusCode::NO_CONTENT
        }
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
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
        let shared = Arc::new(Mutex::new(store));
        let app = router(shared.clone(), tempdir.path().into());

        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "file.txt",
                    "content": "hello",
                    "parent_folder_id": null,
                    "doc_type": "Text"
                })
                .to_string(),
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
                json!({
                    "name": "file.txt",
                    "content": "world",
                    "parent_folder_id": null,
                    "doc_type": "Text"
                })
                .to_string(),
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

        // root folder should exist
        let mut store = shared.lock().await;
        assert!(store.ensure_root("user1").is_ok());
    }

    #[tokio::test]
    async fn folder_listing() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = DocumentStore::new(tempdir.path()).unwrap();
        let shared = Arc::new(Mutex::new(store));
        let app = router(shared.clone(), tempdir.path().into());

        let root = {
            let mut s = shared.lock().await;
            s.ensure_root("user1").unwrap()
        };

        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "folder",
                    "content": "",
                    "parent_folder_id": root,
                    "doc_type": "Folder"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let folder_id = v["id"].as_str().unwrap();

        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "file.txt",
                    "content": "hello",
                    "parent_folder_id": folder_id,
                    "doc_type": "Text"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        let req = Request::builder()
            .uri(format!("/folders/{}", folder_id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(arr.len(), 1); // index guide present
        let types: Vec<_> = arr
            .iter()
            .map(|v| v["doc_type"].as_str().unwrap())
            .collect();
        assert!(types.contains(&"IndexGuide"));
    }

    #[tokio::test]
    async fn create_in_folder_endpoint() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = DocumentStore::new(tempdir.path()).unwrap();
        let shared = Arc::new(Mutex::new(store));
        let app = router(shared.clone(), tempdir.path().into());

        let root = {
            let mut s = shared.lock().await;
            s.ensure_root("user1").unwrap()
        };

        // create a subfolder under root
        let req = Request::builder()
            .method("POST")
            .uri(format!("/folders/{}", root))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({"name": "sub", "type": "folder"}).to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let folder_id = v["id"].as_str().unwrap();

        // create a document inside the subfolder
        let req = Request::builder()
            .method("POST")
            .uri(format!("/folders/{}", folder_id))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "note.txt",
                    "content": "hello",
                    "type": "document"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let doc_id = v["id"].as_str().unwrap();

        // ensure document can be fetched
        let req = Request::builder()
            .uri(format!("/docs/{}", doc_id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn index_guide_endpoint() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = DocumentStore::new(tempdir.path()).unwrap();
        let shared = Arc::new(Mutex::new(store));
        let app = router(shared.clone(), tempdir.path().into());

        let root = {
            let mut s = shared.lock().await;
            s.ensure_root("user1").unwrap()
        };

        // create a subfolder so it has an index guide
        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "sub", "content": "", "parent_folder_id": root,
                    "doc_type": "Folder"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let folder_id = v["id"].as_str().unwrap();

        // fetch the index guide
        let req = Request::builder()
            .uri(format!("/folders/{}/guide", folder_id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let guide: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(guide["doc_type"], "IndexGuide");
    }

    #[tokio::test]
    async fn folder_sharing() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = DocumentStore::new(tempdir.path()).unwrap();
        let shared = Arc::new(Mutex::new(store));
        let app = router(shared.clone(), tempdir.path().into());

        let root = {
            let mut s = shared.lock().await;
            s.ensure_root("user1").unwrap()
        };

        // create a folder and a document inside it
        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "shared", "content": "", "parent_folder_id": root,
                    "doc_type": "Folder"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let folder_id = v["id"].as_str().unwrap();

        let req = Request::builder()
            .method("POST")
            .uri(format!("/folders/{}", folder_id))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({"name": "note.txt", "content": "hi", "type": "document"}).to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let doc_id = v["id"].as_str().unwrap();

        // share the folder with user2
        let req = Request::builder()
            .method("POST")
            .uri(format!("/folders/{}/share", folder_id))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({"user": "user2", "rights": "read"}).to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);

        // user2 should be able to read the document
        let req = Request::builder()
            .uri(format!("/docs/{}", doc_id))
            .header("X-User-Id", "user2")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);

        // revoke access
        let req = Request::builder()
            .method("DELETE")
            .uri(format!("/folders/{}/share", folder_id))
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(json!({"user": "user2"}).to_string()))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NO_CONTENT);

        // user2 should now be forbidden
        let req = Request::builder()
            .uri(format!("/docs/{}", doc_id))
            .header("X-User-Id", "user2")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    }
}
