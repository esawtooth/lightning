use axum::{
    extract::{Request, State},
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::Response,
};
use context_hub_core::auth::TokenVerifier;
use std::sync::Arc;

/// Auth context that will be available in handlers
#[derive(Clone, Debug)]
pub struct AuthContext {
    pub user_id: String,
    pub agent_id: Option<String>,
}

/// Extract auth context from request
pub async fn extract_auth_context(
    headers: &HeaderMap,
    verifier: Arc<dyn TokenVerifier>,
) -> Result<AuthContext, StatusCode> {
    // Try Bearer token first (standard OAuth2/AAD flow)
    if let Some(auth_header) = headers.get("Authorization") {
        if let Ok(auth_str) = auth_header.to_str() {
            if let Some(token) = auth_str.strip_prefix("Bearer ") {
                if let Some(claims) = verifier.verify(token).await {
                    return Ok(AuthContext {
                        user_id: claims.sub,
                        agent_id: claims.agent,
                    });
                }
            }
        }
    }
    
    // Fall back to X-User-Id header for backward compatibility
    // TODO: Remove this once all clients are updated
    if let Some(user_header) = headers.get("X-User-Id") {
        if let Ok(user_id) = user_header.to_str() {
            return Ok(AuthContext {
                user_id: user_id.to_string(),
                agent_id: headers
                    .get("X-Agent-Id")
                    .and_then(|h| h.to_str().ok())
                    .map(String::from),
            });
        }
    }
    
    // No valid auth found
    Err(StatusCode::UNAUTHORIZED)
}

/// Middleware to require authentication
pub async fn require_auth(
    State(verifier): State<Arc<dyn TokenVerifier>>,
    mut request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let auth_context = extract_auth_context(request.headers(), verifier).await?;
    
    // Insert auth context into request extensions
    request.extensions_mut().insert(auth_context);
    
    Ok(next.run(request).await)
}

/// Extension trait for Request to get auth context
pub trait AuthContextExt {
    fn auth_context(&self) -> Option<&AuthContext>;
}

impl AuthContextExt for Request {
    fn auth_context(&self) -> Option<&AuthContext> {
        self.extensions().get::<AuthContext>()
    }
}