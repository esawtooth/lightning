//! Distributed API layer with rate limiting and cluster routing

use crate::auth::distributed::{AuthService, Claims, RateLimiter, TokenPair};
use crate::shard::{ShardId, ShardRouter};
use crate::storage::distributed::DistributedDocumentStore;
use anyhow::Result;
use axum::{
    extract::{FromRequestParts, Path, Query, State},
    http::{request::Parts, HeaderMap, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{delete, get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::sync::Arc;
use tower::ServiceBuilder;
use tower_http::{
    compression::CompressionLayer,
    cors::{Any, CorsLayer},
    trace::TraceLayer,
};
use uuid::Uuid;

/// API state shared across handlers
#[derive(Clone)]
pub struct ApiState {
    pub shard_id: ShardId,
    pub router: Arc<dyn ShardRouter>,
    pub store: Arc<DistributedDocumentStore>,
    pub auth: Arc<AuthService>,
    pub rate_limiter: Arc<RateLimiter>,
}

/// Authenticated request context
#[derive(Clone, Debug)]
pub struct AuthContext {
    pub claims: Claims,
    pub ip_address: String,
}

impl FromRequestParts<ApiState> for AuthContext {
    type Rejection = StatusCode;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &ApiState,
    ) -> Result<Self, Self::Rejection> {
        // Extract bearer token
        let auth_header = parts
            .headers
            .get("Authorization")
            .and_then(|v| v.to_str().ok())
            .ok_or(StatusCode::UNAUTHORIZED)?;
        
        let token = auth_header
            .strip_prefix("Bearer ")
            .ok_or(StatusCode::UNAUTHORIZED)?;
        
        // Verify token
        let claims = state
            .auth
            .verify_token(token)
            .await
            .map_err(|_| StatusCode::UNAUTHORIZED)?;
        
        // Extract IP address
        let ip_address = parts
            .headers
            .get("X-Real-IP")
            .or_else(|| parts.headers.get("X-Forwarded-For"))
            .and_then(|v| v.to_str().ok())
            .unwrap_or("unknown")
            .to_string();
        
        Ok(AuthContext { claims, ip_address })
    }
}

// Request/Response types

#[derive(Deserialize)]
pub struct CreateDocumentRequest {
    pub name: String,
    pub content: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: Option<String>,
    pub encrypted: Option<bool>,
}

#[derive(Serialize)]
pub struct DocumentResponse {
    pub id: Uuid,
    pub name: String,
    pub content: String,
    pub owner: String,
    pub parent_folder_id: Option<Uuid>,
    pub doc_type: String,
    pub version: i64,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct UpdateDocumentRequest {
    pub content: String,
    pub version: Option<i64>, // For optimistic concurrency control
}

#[derive(Deserialize)]
pub struct ShareRequest {
    pub principal: String,
    pub access_level: String,
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
    pub has_more: bool,
}

#[derive(Serialize)]
pub struct DocumentSummary {
    pub id: Uuid,
    pub name: String,
    pub snippet: String,
    pub doc_type: String,
    pub updated_at: String,
}

#[derive(Serialize)]
pub struct ErrorResponse {
    pub error: String,
    pub code: String,
    pub request_id: String,
}

#[derive(Deserialize)]
pub struct LoginRequest {
    pub email: String,
    pub password: String,
}

/// Create the API router
pub fn create_router(state: ApiState) -> Router {
    Router::new()
        // Auth endpoints
        .route("/auth/login", post(login))
        .route("/auth/refresh", post(refresh_token))
        .route("/auth/logout", post(logout))
        
        // Document endpoints
        .route("/documents", post(create_document).get(list_documents))
        .route(
            "/documents/:id",
            get(get_document)
                .put(update_document)
                .delete(delete_document),
        )
        .route("/documents/:id/share", post(share_document))
        .route("/documents/:id/unshare", delete(unshare_document))
        
        // Search
        .route("/search", get(search_documents))
        
        // Health checks
        .route("/health", get(health_check))
        .route("/ready", get(readiness_check))
        
        // Apply middleware
        .layer(
            ServiceBuilder::new()
                .layer(middleware::from_fn_with_state(
                    state.clone(),
                    rate_limit_middleware,
                ))
                .layer(middleware::from_fn(request_id_middleware))
                .layer(TraceLayer::new_for_http())
                .layer(CompressionLayer::new())
                .layer(
                    CorsLayer::new()
                        .allow_origin(Any)
                        .allow_methods(Any)
                        .allow_headers(Any),
                ),
        )
        .with_state(state)
}

// Middleware

async fn rate_limit_middleware(
    State(state): State<ApiState>,
    req: axum::extract::Request,
    next: Next,
) -> Response {
    // Extract identifier for rate limiting
    let identifier = req
        .headers()
        .get("X-Real-IP")
        .or_else(|| req.headers().get("X-Forwarded-For"))
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown");
    
    // Check rate limit
    if !state.rate_limiter.check_rate_limit(identifier).await.unwrap_or(false) {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(ErrorResponse {
                error: "Rate limit exceeded".to_string(),
                code: "RATE_LIMITED".to_string(),
                request_id: Uuid::new_v4().to_string(),
            }),
        )
        .into_response();
    }
    
    next.run(req).await
}

async fn request_id_middleware(
    mut req: axum::extract::Request,
    next: Next,
) -> Response {
    let request_id = Uuid::new_v4().to_string();
    req.headers_mut().insert(
        "X-Request-ID",
        request_id.parse().unwrap(),
    );
    
    let mut response = next.run(req).await;
    response.headers_mut().insert(
        "X-Request-ID",
        request_id.parse().unwrap(),
    );
    
    response
}

// Auth handlers

async fn login(
    State(state): State<ApiState>,
    headers: HeaderMap,
    Json(req): Json<LoginRequest>,
) -> Result<Json<TokenPair>, StatusCode> {
    let ip = headers
        .get("X-Real-IP")
        .or_else(|| headers.get("X-Forwarded-For"))
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown");
    
    let user_agent = headers
        .get("User-Agent")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("unknown");
    
    state
        .auth
        .authenticate(&req.email, &req.password, ip, user_agent)
        .await
        .map(Json)
        .map_err(|_| StatusCode::UNAUTHORIZED)
}

async fn refresh_token(
    State(state): State<ApiState>,
    headers: HeaderMap,
) -> Result<Json<TokenPair>, StatusCode> {
    let auth_header = headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .ok_or(StatusCode::UNAUTHORIZED)?;
    
    let token = auth_header
        .strip_prefix("Bearer ")
        .ok_or(StatusCode::UNAUTHORIZED)?;
    
    state
        .auth
        .refresh_token(token)
        .await
        .map(Json)
        .map_err(|_| StatusCode::UNAUTHORIZED)
}

async fn logout(
    State(state): State<ApiState>,
    auth: AuthContext,
) -> StatusCode {
    if state.auth.logout(&auth.claims.sid).await.is_ok() {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

// Document handlers

async fn create_document(
    State(state): State<ApiState>,
    auth: AuthContext,
    Json(req): Json<CreateDocumentRequest>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    // Check if user is on this shard
    if auth.claims.shard != state.shard_id.0 {
        // Proxy to correct shard
        return Err(StatusCode::TEMPORARY_REDIRECT);
    }
    
    let doc_type = req.doc_type.unwrap_or_else(|| "Text".to_string());
    
    let doc_id = state
        .store
        .create(
            &auth.claims.sub,
            req.name.clone(),
            &req.content,
            req.parent_folder_id,
            crate::storage::crdt::DocumentType::from_str(&doc_type),
        )
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    
    // Load created document
    let doc = state
        .store
        .get(&auth.claims.sub, doc_id)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    
    Ok(Json(DocumentResponse {
        id: doc_id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: doc.owner().to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type,
        version: 1,
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
    }))
}

async fn get_document(
    State(state): State<ApiState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> Result<Json<DocumentResponse>, StatusCode> {
    let doc = state
        .store
        .get(&auth.claims.sub, id)
        .await
        .map_err(|_| StatusCode::NOT_FOUND)?;
    
    Ok(Json(DocumentResponse {
        id,
        name: doc.name().to_string(),
        content: doc.text(),
        owner: doc.owner().to_string(),
        parent_folder_id: doc.parent_folder_id(),
        doc_type: doc.doc_type().as_str().to_string(),
        version: 1, // Would track actual version
        created_at: chrono::Utc::now().to_rfc3339(),
        updated_at: chrono::Utc::now().to_rfc3339(),
    }))
}

async fn update_document(
    State(state): State<ApiState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateDocumentRequest>,
) -> StatusCode {
    if state
        .store
        .update(&auth.claims.sub, id, &req.content)
        .await
        .is_ok()
    {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn delete_document(
    State(state): State<ApiState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
) -> StatusCode {
    if state.store.delete(&auth.claims.sub, id).await.is_ok() {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn share_document(
    State(state): State<ApiState>,
    auth: AuthContext,
    Path(id): Path<Uuid>,
    Json(req): Json<ShareRequest>,
) -> StatusCode {
    let access = match req.access_level.as_str() {
        "read" => crate::storage::crdt::AccessLevel::Read,
        "write" => crate::storage::crdt::AccessLevel::Write,
        _ => return StatusCode::BAD_REQUEST,
    };
    
    if state
        .store
        .update_acl(&auth.claims.sub, id, req.principal, access)
        .await
        .is_ok()
    {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::INTERNAL_SERVER_ERROR
    }
}

async fn unshare_document(
    State(_state): State<ApiState>,
    _auth: AuthContext,
    Path(_id): Path<Uuid>,
    Query(_params): Query<ShareRequest>,
) -> StatusCode {
    // Would implement ACL removal
    StatusCode::NO_CONTENT
}

async fn list_documents(
    State(_state): State<ApiState>,
    _auth: AuthContext,
) -> Result<Json<Vec<DocumentSummary>>, StatusCode> {
    // Would implement document listing with pagination
    Ok(Json(vec![]))
}

async fn search_documents(
    State(_state): State<ApiState>,
    _auth: AuthContext,
    Query(_params): Query<SearchQuery>,
) -> Result<Json<SearchResult>, StatusCode> {
    // Would implement search across user's documents
    Ok(Json(SearchResult {
        documents: vec![],
        total: 0,
        has_more: false,
    }))
}

// Health checks

async fn health_check() -> &'static str {
    "OK"
}

async fn readiness_check(State(state): State<ApiState>) -> StatusCode {
    // Check if shard is ready to serve traffic
    match state.router.shard_info(state.shard_id).await {
        Ok(info) if info.status == crate::shard::ShardStatus::Active => StatusCode::OK,
        _ => StatusCode::SERVICE_UNAVAILABLE,
    }
}

/// Run the API server
pub async fn run_server(
    addr: SocketAddr,
    state: ApiState,
) -> Result<()> {
    let app = create_router(state);
    
    println!("Starting API server on {}", addr);
    
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    
    Ok(())
}