//! Compress API endpoints for manual compression and status monitoring

use axum::{
    extract::State,
    response::Json,
    http::StatusCode,
};
use serde::Serialize;
use crate::api::legacy::ApiState;

#[derive(Debug, Serialize)]
pub struct CompressResponse {
    pub message: String,
    pub stats: Option<CompressStatsResponse>,
}

#[derive(Debug, Serialize)]
pub struct CompressStatsResponse {
    pub started_at: String,
    pub completed_at: String,
    pub duration_secs: f64,
    pub snapshot_id: String,
    pub storage_before_mb: f64,
    pub storage_after_mb: f64,
    pub bytes_freed_mb: f64,
    pub documents_removed: usize,
    pub blobs_removed: usize,
    pub wal_entries_removed: usize,
    pub index_docs_removed: usize,
}

#[derive(Debug, Serialize)]
pub struct StorageResponse {
    pub current_size_mb: f64,
    pub last_snapshot_size_mb: f64,
    pub growth_percentage: f64,
    pub should_compress: bool,
    pub components: std::collections::HashMap<String, f64>,
    pub last_compress: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CompressStatusResponse {
    pub last_compress: Option<CompressStatsResponse>,
    pub current_storage: StorageResponse,
    pub config: CompressConfigResponse,
}

#[derive(Debug, Serialize)]
pub struct CompressConfigResponse {
    pub threshold_percent: f64,
    pub min_interval_secs: u64,
    pub max_interval_secs: u64,
    pub snapshot_retention: usize,
}

/// Manually trigger compression
pub async fn compress(
    State(_state): State<ApiState>,
) -> Result<Json<CompressResponse>, (StatusCode, String)> {
    // Compress service is not available in multi-threaded Axum context
    // due to git2::Repository thread safety limitations
    Err((
        StatusCode::SERVICE_UNAVAILABLE,
        "Compress service not available in web API due to thread safety limitations. Use compress_monitor_task in LocalSet context instead.".to_string(),
    ))
}

/// Get current storage metrics
pub async fn storage_metrics(
    State(_state): State<ApiState>,
) -> Result<Json<StorageResponse>, (StatusCode, String)> {
    Err((
        StatusCode::SERVICE_UNAVAILABLE,
        "Storage metrics not available in web API due to thread safety limitations.".to_string(),
    ))
}

/// Get compression status and configuration
pub async fn compress_status(
    State(_state): State<ApiState>,
) -> Result<Json<CompressStatusResponse>, (StatusCode, String)> {
    Err((
        StatusCode::SERVICE_UNAVAILABLE,
        "Compress status not available in web API due to thread safety limitations.".to_string(),
    ))
}

/// Register compress routes with the Axum router
pub fn routes() -> axum::Router<ApiState> {
    use axum::routing::{get, post};
    
    axum::Router::new()
        .route("/api/admin/compress", post(compress))
        .route("/api/admin/storage", get(storage_metrics))
        .route("/api/admin/compress/status", get(compress_status))
}