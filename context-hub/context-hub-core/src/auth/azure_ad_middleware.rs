use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use super::azure_ad::{AzureADAuthenticator, AzureADClaims};

/// Azure AD authentication middleware for Axum
pub async fn require_azure_ad_auth(
    State(auth): State<AzureADAuthenticator>,
    mut request: Request,
    next: Next,
) -> Result<Response, AuthError> {
    // Extract bearer token
    let token = extract_bearer_token(&request)?;
    
    // Validate token with Azure AD
    let claims = auth.validate_token(&token)
        .await
        .map_err(|e| AuthError::InvalidToken(e.to_string()))?;
    
    // Check if user is authorized
    check_authorization(&claims)?;
    
    // Create auth context
    let auth_context = AuthContext {
        user_id: claims.oid.clone(),
        tenant_id: claims.tid.clone(),
        email: claims.preferred_username.clone(),
        name: claims.name.clone(),
        roles: claims.roles.unwrap_or_default(),
        groups: claims.groups.unwrap_or_default(),
    };
    
    // Insert auth context into request extensions
    request.extensions_mut().insert(auth_context);
    
    Ok(next.run(request).await)
}

/// Extract bearer token from request
fn extract_bearer_token(request: &Request) -> Result<String, AuthError> {
    request
        .headers()
        .get("Authorization")
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "))
        .map(String::from)
        .ok_or(AuthError::MissingToken)
}

/// Check if user is authorized based on claims
fn check_authorization(claims: &AzureADClaims) -> Result<(), AuthError> {
    // Check if user has required role
    if let Some(roles) = &claims.roles {
        if !roles.iter().any(|r| r == "ContextHub.User" || r == "ContextHub.Admin") {
            return Err(AuthError::InsufficientPermissions(
                "User must have ContextHub.User or ContextHub.Admin role".to_string()
            ));
        }
    }
    
    // Additional checks can be added here (groups, licenses, etc.)
    
    Ok(())
}

/// Auth context that will be available in handlers
#[derive(Clone, Debug)]
pub struct AuthContext {
    pub user_id: String,
    pub tenant_id: String,
    pub email: String,
    pub name: String,
    pub roles: Vec<String>,
    pub groups: Vec<String>,
}

impl AuthContext {
    pub fn is_admin(&self) -> bool {
        self.roles.iter().any(|r| r == "ContextHub.Admin")
    }
    
    pub fn has_role(&self, role: &str) -> bool {
        self.roles.iter().any(|r| r == role)
    }
}

/// Auth errors
#[derive(Debug)]
pub enum AuthError {
    MissingToken,
    InvalidToken(String),
    InsufficientPermissions(String),
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AuthError::MissingToken => (
                StatusCode::UNAUTHORIZED,
                "Missing authentication token"
            ),
            AuthError::InvalidToken(msg) => (
                StatusCode::UNAUTHORIZED,
                &msg
            ),
            AuthError::InsufficientPermissions(msg) => (
                StatusCode::FORBIDDEN,
                &msg
            ),
        };
        
        let body = Json(json!({
            "error": message,
            "status": status.as_u16()
        }));
        
        (status, body).into_response()
    }
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

/// Middleware for tenant isolation
pub async fn enforce_tenant_isolation(
    mut request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    // Get auth context
    let auth_context = request.extensions().get::<AuthContext>()
        .ok_or(StatusCode::UNAUTHORIZED)?;
    
    // Get requested document/resource
    if let Some(doc_id) = request.uri().path().split('/').last() {
        // In a real implementation, check if resource belongs to user's tenant
        // For now, we'll inject tenant filter into query
        request.extensions_mut().insert(TenantFilter {
            tenant_id: auth_context.tenant_id.clone(),
        });
    }
    
    Ok(next.run(request).await)
}

#[derive(Clone)]
pub struct TenantFilter {
    pub tenant_id: String,
}

/// Helper middleware for admin-only endpoints
pub async fn require_admin(
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let auth_context = request.extensions().get::<AuthContext>()
        .ok_or(StatusCode::UNAUTHORIZED)?;
    
    if !auth_context.is_admin() {
        return Err(StatusCode::FORBIDDEN);
    }
    
    Ok(next.run(request).await)
}