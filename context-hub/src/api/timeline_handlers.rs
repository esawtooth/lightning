use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::Json,
};
use context_hub_core::timeline::{
    TimelineState, TimelineInfo, ChangeDensity, DocumentState, TimelineChange
};
use serde::Deserialize;
use chrono::{DateTime, Utc};

#[derive(Deserialize)]
pub struct StateQuery {
    pub timestamp: DateTime<Utc>,
}

#[derive(Deserialize)]
pub struct ChangesQuery {
    pub resolution: Option<String>,
}

pub async fn get_timeline_info(
    State(state): State<TimelineState>,
) -> Result<Json<TimelineInfo>, StatusCode> {
    let index = state.index.read().await;
    
    let (start_time, end_time) = if let (Some(first), Some(last)) = 
        (index.snapshots.keys().next(), index.snapshots.keys().last()) {
        (*first, *last)
    } else {
        return Err(StatusCode::NO_CONTENT);
    };
    
    Ok(Json(TimelineInfo {
        start_time,
        end_time,
        total_duration_ms: (end_time - start_time).num_milliseconds(),
        snapshot_count: index.snapshots.len(),
        change_density: ChangeDensity {
            buckets: index.activity_buckets.clone(),
            bucket_size_ms: 3600000,
        },
    }))
}

pub async fn get_timeline_changes(
    Query(_params): Query<ChangesQuery>,
    State(state): State<TimelineState>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let index = state.index.read().await;
    
    let changes: Vec<&TimelineChange> = index.changes
        .values()
        .flat_map(|v| v)
        .collect();
    
    Ok(Json(serde_json::json!({
        "changes": changes
    })))
}

pub async fn get_state_at_timestamp(
    Query(params): Query<StateQuery>,
    State(state): State<TimelineState>,
) -> Result<Json<DocumentState>, StatusCode> {
    match state.reconstructor.get_state_at(params.timestamp).await {
        Ok(doc_state) => Ok(Json(doc_state)),
        Err(_) => Err(StatusCode::INTERNAL_SERVER_ERROR),
    }
}