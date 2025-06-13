//! HTTP API layer exposing document CRUD endpoints.

use crate::auth::TokenVerifier;
use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        FromRequestParts, Path, Query, State,
    },
    http::{request::Parts, StatusCode},
    routing::{get, post, put},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};
use uuid::Uuid;

use crate::events::{Event, EventBus};
use crate::indexer::LiveIndex;
use crate::snapshot::SnapshotManager;
use crate::storage::crdt::{AccessLevel, DocumentStore, DocumentType, Pointer};
use std::collections::HashMap;
use std::path::PathBuf;
use tokio::sync::broadcast;
use futures::SinkExt;
use bytes::Bytes;

/// Authentication context extracted from request headers.
#[derive(Clone, Debug)]
pub struct AuthContext {
    pub user_id: String,
    pub agent_id: Option<String>,
}

impl FromRequestParts<AppState> for AuthContext {
    type Rejection = StatusCode;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let headers = &parts.headers;
        if let Some(auth) = headers.get("Authorization").and_then(|v| v.to_str().ok()) {
            if let Some(token) = auth.strip_prefix("Bearer ") {
                if let Some(claims) = state.verifier.verify(token).await {
                    return Ok(Self {
                        user_id: claims.sub,
                        agent_id: claims.agent,
                    });
                }
            }
        }
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
    pub store: Arc<RwLock<DocumentStore>>,
    pub snapshot_dir: PathBuf,
    pub snapshot_retention: Option<usize>,
    pub indexer: Arc<LiveIndex>,
    pub events: crate::events::EventBus,
    pub verifier: Arc<dyn TokenVerifier>,
    pub channels: Arc<Mutex<std::collections::HashMap<Uuid, broadcast::Sender<Vec<u8>>>>>,
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

#[derive(Serialize)]
struct BlobResponse {
    id: String,
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

#[derive(Deserialize)]
struct RenameRequest {
    name: String,
}

#[derive(Deserialize)]
struct MoveRequest {
    new_parent_folder_id: Uuid,
}

#[derive(Deserialize)]
struct SearchParams {
    q: String,
    limit: Option<usize>,
}

#[derive(Serialize)]
struct SearchResult {
    id: Uuid,
    name: String,
    snippet: String,
}

#[derive(Serialize)]
struct SnapshotEntry {
    id: String,
    timestamp: String,
}

#[derive(Serialize)]
struct RootResponse {
    id: Uuid,
}

pub fn router(
    state: Arc<RwLock<DocumentStore>>,
    snapshot_dir: PathBuf,
    snapshot_retention: Option<usize>,
    indexer: Arc<LiveIndex>,
    events: EventBus,
    verifier: Arc<dyn TokenVerifier>,
) -> Router {
    let app_state = AppState {
        store: state,
        snapshot_dir,
        snapshot_retention,
        indexer,
        events,
        verifier,
        channels: Arc::new(Mutex::new(HashMap::new())),
    };
    Router::new()
        .route("/docs", post(create_doc))
        .route(
            "/docs/{id}",
            get(get_doc).put(update_doc).delete(delete_doc),
        )
        .route("/docs/{id}/move", put(move_doc))
        .route("/docs/{id}/rename", put(rename_doc))
        .route("/docs/{id}/content", post(upload_blob))
        .route("/docs/{id}/content/{idx}", get(get_blob))
        .route("/docs/{id}/resolve_pointer", get(resolve_pointer))
        .route("/docs/{id}/guide", get(get_index_guide))
        .route("/folders/{id}", get(list_folder).post(create_in_folder))
        .route(
            "/folders/{id}/share",
            post(share_folder).delete(unshare_folder),
        )
        .route(
            "/agents/{id}/scopes",
            post(set_agent_scope).delete(clear_agent_scope),
        )
        .route("/docs/{id}/sharing", get(list_sharing))
        .route("/search", get(search_docs))
        .route("/snapshot", post(snapshot_now))
        .route("/restore", post(restore_snapshot))
        .route("/snapshots", get(list_snapshots))
        .route("/snapshots/{rev}/docs/{id}", get(get_snapshot_doc))
        .route("/root", get(get_root))
        .route("/ws", get(ws_stream))
        .route("/ws/docs/{id}", get(doc_ws))
        .with_state(app_state)
}

async fn create_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Json(req): Json<DocRequest>,
) -> Result<Json<DocResponse>, StatusCode> {
    let mut store = state.store.write().await;
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
    let extra = if doc_type == DocumentType::Folder {
        store.index_guide_id(id)
    } else {
        None
    };
    drop(store);
    state.indexer.schedule_update(id).await;
    if let Some(eid) = extra {
        state.indexer.schedule_update(eid).await;
    }
    state.events.send(Event::Created { id });
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
    let mut store = state.store.write().await;
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
    let mut store = state.store.write().await;
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
                drop(store);
                state.indexer.schedule_update(id).await;
                state.events.send(Event::Updated { id });
                if let Some(tx) = state.channels.lock().await.get(&id).cloned() {
                    let _ = tx.send(req.content.clone().into_bytes());
                }
                StatusCode::NO_CONTENT
            } else {
                StatusCode::FORBIDDEN
            }
        }
        None => StatusCode::NOT_FOUND,
    }
}

async fn rename_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<RenameRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(_) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                let _ = store.rename(id, req.name);
                drop(store);
                state.indexer.schedule_update(id).await;
                state.events.send(Event::Updated { id });
                StatusCode::NO_CONTENT
            } else {
                StatusCode::FORBIDDEN
            }
        }
        None => StatusCode::NOT_FOUND,
    }
}

async fn move_doc(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<MoveRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(_) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) && store.has_permission(
                req.new_parent_folder_id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                let ids = store.descendant_ids(id);
                match store.move_item(id, req.new_parent_folder_id) {
                    Ok(_) => {
                        drop(store);
                        state.indexer.schedule_recursive_update(ids).await;
                        state.events.send(Event::Moved {
                            id,
                            new_parent: req.new_parent_folder_id,
                        });
                        StatusCode::NO_CONTENT
                    }
                    Err(_) => StatusCode::BAD_REQUEST,
                }
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
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(_) => {
            if store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Write,
            ) {
                let mut ids = Vec::new();
                fn gather(store: &DocumentStore, id: Uuid, out: &mut Vec<Uuid>) {
                    out.push(id);
                    if let Some(doc) = store.get(id) {
                        if doc.doc_type() == DocumentType::Folder {
                            for child in doc.child_ids() {
                                gather(store, child, out);
                            }
                        }
                    }
                }
                gather(&store, id, &mut ids);
                match store.delete(id) {
                    Ok(_) => {
                        drop(store);
                        state.indexer.schedule_recursive_delete(ids).await;
                        state.events.send(Event::Deleted { id });
                        StatusCode::NO_CONTENT
                    }
                    Err(_) => StatusCode::BAD_REQUEST,
                }
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
    let mut store = state.store.write().await;
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
                let extra = store.index_guide_id(id);
                drop(store);
                state.indexer.schedule_update(id).await;
                if let Some(eid) = extra {
                    state.indexer.schedule_update(eid).await;
                }
                state.events.send(Event::Created { id });
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
                drop(store);
                state.indexer.schedule_update(id).await;
                state.events.send(Event::Created { id });
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
    let mut store = state.store.write().await;
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
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.get(id) {
        Some(doc) => {
            if !store.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Read,
            ) {
                return Err(StatusCode::FORBIDDEN);
            }
            let folder_id = if doc.doc_type() == DocumentType::Folder {
                id
            } else {
                match doc.parent_folder_id() {
                    Some(fid) => fid,
                    None => return Err(StatusCode::NOT_FOUND),
                }
            };
            if let Some(guide_id) = store.index_guide_id(folder_id) {
                if let Some(guide) = store.get(guide_id) {
                    let guides = store.collect_index_guides(id);
                    let mut content = String::new();
                    for (path, text) in guides {
                        content.push_str(&format!("# {}\n{}\n\n", path, text));
                    }
                    return Ok(Json(DocResponse {
                        id: guide_id,
                        name: guide.name().to_string(),
                        content,
                        parent_folder_id: guide.parent_folder_id(),
                        doc_type: guide.doc_type(),
                        owner: guide.owner().to_string(),
                    }));
                }
            }
            Err(StatusCode::NOT_FOUND)
        }
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn search_docs(
    State(state): State<AppState>,
    auth: AuthContext,
    Query(params): Query<SearchParams>,
) -> Result<Json<Vec<SearchResult>>, StatusCode> {
    let limit = params.limit.unwrap_or(10);
    let ids = state
        .indexer
        .search(&params.q, limit)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let store_guard = state.store.read().await;
    let mut results = Vec::new();
    for id in ids {
        if let Some(doc) = store_guard.get(id) {
            if store_guard.has_permission(
                id,
                &auth.user_id,
                auth.agent_id.as_deref(),
                AccessLevel::Read,
            ) {
                let snippet: String = doc.text().chars().take(100).collect();
                results.push(SearchResult {
                    id,
                    name: doc.name().to_string(),
                    snippet,
                });
            }
        }
    }
    Ok(Json(results))
}

async fn get_root(
    State(state): State<AppState>,
    auth: AuthContext,
) -> Result<Json<RootResponse>, StatusCode> {
    let mut store = state.store.write().await;
    let id = store.ensure_root(&auth.user_id).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(RootResponse { id }))
}

#[derive(Deserialize)]
struct UploadParams {
    name: Option<String>,
}

async fn upload_blob(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Query(params): Query<UploadParams>,
    body: axum::body::Bytes,
) -> Result<Json<BlobResponse>, StatusCode> {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Write,
    ) {
        return Err(StatusCode::FORBIDDEN);
    }
    let blob_id = Uuid::new_v4().to_string();
    let pointer = Pointer {
        pointer_type: "blob".to_string(),
        target: blob_id.clone(),
        name: params.name,
        preview_text: None,
    };
    store
        .store_data(&pointer, &body)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let index = store.content_len(id).unwrap_or(0);
    store
        .insert_pointer(id, index, pointer)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    drop(store);
    state.indexer.schedule_update(id).await;
    Ok(Json(BlobResponse { id: blob_id }))
}

async fn get_blob(
    State(state): State<AppState>,
    auth: AuthContext,
    Path((id, idx)): Path<(Uuid, usize)>,
) -> Result<(StatusCode, axum::body::Bytes), StatusCode> {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Read,
    ) {
        return Err(StatusCode::FORBIDDEN);
    }
    let data = store
        .resolve_pointer(id, idx)
        .map_err(|_| StatusCode::NOT_FOUND)?;
    Ok((StatusCode::OK, axum::body::Bytes::from(data)))
}

#[derive(Deserialize)]
struct ResolveParams {
    name: String,
}

async fn resolve_pointer(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Query(params): Query<ResolveParams>,
) -> Result<(StatusCode, axum::body::Bytes), StatusCode> {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Read,
    ) {
        return Err(StatusCode::FORBIDDEN);
    }
    let data = store
        .resolve_pointer_by_name(id, &params.name)
        .map_err(|_| StatusCode::NOT_FOUND)?;
    Ok((StatusCode::OK, axum::body::Bytes::from(data)))
}

async fn share_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<ShareRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
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
    let principal = req.user.clone();
    let _ = store.add_acl(id, req.user, level);
    state.events.send(Event::Shared { id, principal });
    StatusCode::NO_CONTENT
}

async fn unshare_folder(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<UnshareRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Write,
    ) {
        return StatusCode::FORBIDDEN;
    }
    let principal = req.user.clone();
    let _ = store.remove_acl(id, &req.user);
    state.events.send(Event::Unshared { id, principal });
    StatusCode::NO_CONTENT
}

#[derive(Deserialize)]
struct AgentScopeRequest {
    folders: Vec<Uuid>,
}

async fn set_agent_scope(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(agent): Path<String>,
    Json(req): Json<AgentScopeRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.set_agent_scope(auth.user_id.clone(), agent, req.folders) {
        Ok(_) => StatusCode::NO_CONTENT,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn clear_agent_scope(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(agent): Path<String>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    match store.clear_agent_scope(&auth.user_id, &agent) {
        Ok(_) => StatusCode::NO_CONTENT,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn list_sharing(
    State(state): State<AppState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<Vec<crate::storage::crdt::AclEntry>>, StatusCode> {
    let mut store = state.store.write().await;
    let _ = store.ensure_root(&auth.user_id);
    if !store.has_permission(
        id,
        &auth.user_id,
        auth.agent_id.as_deref(),
        AccessLevel::Read,
    ) {
        return Err(StatusCode::FORBIDDEN);
    }
    match store.get(id) {
        Some(doc) => Ok(Json(doc.acl().to_vec())),
        None => Err(StatusCode::NOT_FOUND),
    }
}

async fn snapshot_now(State(state): State<AppState>, _auth: AuthContext) -> StatusCode {
    let mut store = state.store.write().await;
    let mgr = match SnapshotManager::new(&state.snapshot_dir) {
        Ok(m) => m,
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR,
    };
    match mgr.snapshot(&store) {
        Ok(_) => {
            if let Some(max) = state.snapshot_retention {
                let _ = mgr.prune_old_tags(max);
            }
            store.clear_dirty();
            let _ = store.compact_history();
            StatusCode::NO_CONTENT
        }
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

#[derive(Deserialize)]
struct RestoreRequest {
    revision: String,
}

async fn restore_snapshot(
    State(state): State<AppState>,
    _auth: AuthContext,
    Json(req): Json<RestoreRequest>,
) -> StatusCode {
    let mut store = state.store.write().await;
    let mgr = match SnapshotManager::new(&state.snapshot_dir) {
        Ok(m) => m,
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR,
    };
    match mgr.restore(&mut store, &req.revision) {
        Ok(_) => StatusCode::NO_CONTENT,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn list_snapshots(
    State(state): State<AppState>,
    _auth: AuthContext,
) -> Result<Json<Vec<SnapshotEntry>>, StatusCode> {
    let mgr = SnapshotManager::new(&state.snapshot_dir).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let history = mgr
        .history(state.snapshot_retention.unwrap_or(100))
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let entries = history
        .into_iter()
        .map(|h| SnapshotEntry {
            id: h.id.to_string(),
            timestamp: h.time.to_rfc3339(),
        })
        .collect();
    Ok(Json(entries))
}

async fn get_snapshot_doc(
    State(state): State<AppState>,
    Path((rev, id)): Path<(String, Uuid)>,
    _auth: AuthContext,
) -> Result<Json<DocResponse>, StatusCode> {
    let mgr = SnapshotManager::new(&state.snapshot_dir).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    if let Some(doc) = mgr
        .load_document_at(id, &rev)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    {
        Ok(Json(DocResponse {
            id,
            name: doc.name().to_string(),
            content: doc.text(),
            parent_folder_id: doc.parent_folder_id(),
            doc_type: doc.doc_type(),
            owner: doc.owner().to_string(),
        }))
    } else {
        Err(StatusCode::NOT_FOUND)
    }
}

use axum::response::sse::{self, Sse};
use futures::{Stream, StreamExt};
use std::convert::Infallible;

async fn ws_stream(
    State(state): State<AppState>,
    auth: AuthContext,
) -> Sse<impl Stream<Item = Result<sse::Event, Infallible>>> {
    let rx = state.events.subscribe();
    let store = state.store.clone();
    let user = auth.user_id.clone();
    let agent = auth.agent_id.clone();
    let stream = tokio_stream::wrappers::BroadcastStream::new(rx).filter_map(move |res| {
        let store = store.clone();
        let user = user.clone();
        let agent = agent.clone();
        async move {
            match res {
                Ok(evt) => {
                    let id = match &evt {
                        Event::Created { id }
                        | Event::Updated { id }
                        | Event::Deleted { id }
                        | Event::Moved { id, .. }
                        | Event::Shared { id, .. }
                        | Event::Unshared { id, .. } => *id,
                    };
                    let allow = {
                        let store_guard = store.read().await;
                        store_guard.has_permission(id, &user, agent.as_deref(), AccessLevel::Read)
                    };
                    if allow {
                        let data = serde_json::to_string(&evt).ok()?;
                        Some(Ok(sse::Event::default().data(data)))
                    } else {
                        None
                    }
                }
                Err(_) => None,
            }
        }
    });
    Sse::new(stream)
}

async fn doc_ws(
    ws: WebSocketUpgrade,
    Path(id): Path<Uuid>,
    State(state): State<AppState>,
    auth: AuthContext,
) -> impl axum::response::IntoResponse {
    ws.on_upgrade(move |socket| async move {
        handle_doc_ws(socket, id, state, auth).await;
    })
}

async fn handle_doc_ws(mut socket: WebSocket, id: Uuid, state: AppState, auth: AuthContext) {
    let allow = {
        let store = state.store.read().await;
        store.has_permission(
            id,
            &auth.user_id,
            auth.agent_id.as_deref(),
            AccessLevel::Read,
        )
    };
    if !allow {
        let _ = socket.close().await;
        return;
    }

    let tx = {
        let mut map = state.channels.lock().await;
        map.entry(id)
            .or_insert_with(|| {
                let (tx, _) = broadcast::channel(100);
                tx
            })
            .clone()
    };
    let mut rx = tx.subscribe();

    if let Some(snapshot) = {
        let store = state.store.read().await;
        store.get(id).and_then(|d| d.snapshot_bytes().ok())
    } {
        let _ = socket.send(Message::Binary(Bytes::from(snapshot))).await;
    }

    loop {
        tokio::select! {
            msg = socket.recv() => {
                match msg {
                    Some(Ok(Message::Binary(patch))) => {
                        let mut store = state.store.write().await;
                        let _ = store.apply_updates(id, &patch);
                        let _ = tx.send(patch.to_vec());
                        state.indexer.schedule_update(id).await;
                        state.events.send(Event::Updated { id });
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
            res = rx.recv() => {
                if let Ok(patch) = res {
                    if socket.send(Message::Binary(Bytes::from(patch))).await.is_err() {
                        break;
                    }
                } else {
                    break;
                }
            }
        }
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
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

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
        let mut store_guard = store.write().await;
        assert!(store_guard.ensure_root("user1").is_ok());
    }

    #[tokio::test]
    async fn folder_listing() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

        let root = {
            let mut s = store.write().await;
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
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

        let root = {
            let mut s = store.write().await;
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
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

        let root = {
            let mut s = store.write().await;
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
            .uri(format!("/docs/{}/guide", folder_id))
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
    async fn guide_chain_via_index_endpoint() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

        let root = {
            let mut s = store.write().await;
            s.ensure_root("user1").unwrap()
        };

        // create nested folders so both have guides
        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "parent", "content": "", "parent_folder_id": root,
                    "doc_type": "Folder"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let parent_id = v["id"].as_str().unwrap();

        let req = Request::builder()
            .method("POST")
            .uri("/docs")
            .header("X-User-Id", "user1")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({
                    "name": "child", "content": "", "parent_folder_id": parent_id,
                    "doc_type": "Folder"
                })
                .to_string(),
            ))
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
        let child_id = v["id"].as_str().unwrap();

        // call the guide endpoint for the child folder which returns the chain
        let req = Request::builder()
            .uri(format!("/docs/{}/guide", child_id))
            .header("X-User-Id", "user1")
            .body(Body::empty())
            .unwrap();
        let resp = app.clone().oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
        let guide: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert!(guide["content"].as_str().unwrap().contains("parent"));
    }

    #[tokio::test]
    async fn folder_sharing() {
        let tempdir = tempfile::tempdir().unwrap();
        let store = Arc::new(RwLock::new(DocumentStore::new(tempdir.path()).unwrap()));
        let index_dir = tempdir.path().join("index");
        std::fs::create_dir_all(&index_dir).unwrap();
        let search = Arc::new(crate::search::SearchIndex::new(&index_dir).unwrap());
        let indexer = Arc::new(crate::indexer::LiveIndex::new(
            search.clone(),
            store.clone(),
        ));
        let events = crate::events::EventBus::new();
        let verifier = Arc::new(crate::auth::Hs256Verifier::new("secret".into()));
        let app = router(
            store.clone(),
            tempdir.path().into(),
            None,
            indexer,
            events,
            verifier,
        );

        let root = {
            let mut s = store.write().await;
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
