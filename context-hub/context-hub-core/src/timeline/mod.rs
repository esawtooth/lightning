use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::snapshot::SnapshotManager;
use crate::storage::crdt::DocumentStore;

#[cfg(test)]
mod tests;


/// Represents a change event on the timeline
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineChange {
    pub timestamp: DateTime<Utc>,
    pub offset_ms: i64,
    #[serde(rename = "type")]
    pub change_type: ChangeType,
    pub summary: String,
    pub document_ids: Vec<Uuid>,
    pub magnitude: ChangeMagnitude,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeType {
    DocumentCreated,
    DocumentModified,
    DocumentDeleted,
    BulkUpdate,
    FolderCreated,
    FolderDeleted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeMagnitude {
    Minor,    // Single document change
    Moderate, // 2-10 documents
    Major,    // >10 documents or structural changes
}

/// Timeline index for fast temporal queries
pub struct TimelineIndex {
    /// B-tree for O(log n) timestamp lookups
    pub snapshots: BTreeMap<DateTime<Utc>, SnapshotRef>,
    
    /// Change event index
    pub changes: BTreeMap<DateTime<Utc>, Vec<TimelineChange>>,
    
    /// Document lifecycle index
    pub document_lifecycles: HashMap<Uuid, DocumentLifecycle>,
    
    /// Activity density for heatmap visualization
    pub activity_buckets: Vec<ActivityBucket>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SnapshotRef {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub document_count: usize,
}

#[derive(Debug, Clone)]
pub struct DocumentLifecycle {
    pub document_id: Uuid,
    pub events: Vec<LifecycleEvent>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LifecycleEvent {
    pub timestamp: DateTime<Utc>,
    pub event_type: LifecycleEventType,
    pub offset_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LifecycleEventType {
    Created,
    Modified,
    Deleted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityBucket {
    pub start: i64,
    pub end: i64,
    pub change_count: usize,
}

impl TimelineIndex {
    pub fn new() -> Self {
        Self {
            snapshots: BTreeMap::new(),
            changes: BTreeMap::new(),
            document_lifecycles: HashMap::new(),
            activity_buckets: Vec::new(),
        }
    }
    
    /// Find the nearest snapshot before or at the given timestamp
    pub fn find_nearest_snapshot(&self, timestamp: DateTime<Utc>) -> Option<&SnapshotRef> {
        self.snapshots
            .range(..=timestamp)
            .last()
            .map(|(_, snapshot)| snapshot)
    }
    
    /// Get all changes between two timestamps
    pub fn get_changes_between(&self, start: DateTime<Utc>, end: DateTime<Utc>) -> Vec<&TimelineChange> {
        self.changes
            .range(start..=end)
            .flat_map(|(_, events)| events)
            .collect()
    }
    
    /// Build index from snapshot history
    pub async fn build_from_snapshots(&mut self, snapshot_mgr: &SnapshotManager) -> anyhow::Result<()> {
        let history = snapshot_mgr.history(1000)?;
        
        // Index snapshots
        for info in &history {
            self.snapshots.insert(
                info.time,
                SnapshotRef {
                    id: info.id.to_string(),
                    timestamp: info.time,
                    document_count: 0, // Would need to load to get actual count
                },
            );
        }
        
        // Compute changes between consecutive snapshots
        for window in history.windows(2) {
            let (older, newer) = (&window[1], &window[0]);
            self.compute_changes_between(snapshot_mgr, older, newer).await?;
        }
        
        // Build activity buckets
        self.compute_activity_buckets();
        
        Ok(())
    }
    
    async fn compute_changes_between(
        &mut self,
        _snapshot_mgr: &SnapshotManager,
        _older: &crate::snapshot::SnapshotInfo,
        newer: &crate::snapshot::SnapshotInfo,
    ) -> anyhow::Result<()> {
        // This would load both snapshots and compute the diff
        // For now, we'll create synthetic changes
        let changes = vec![
            TimelineChange {
                timestamp: newer.time,
                offset_ms: 0, // Would calculate from start
                change_type: ChangeType::DocumentModified,
                summary: "Document updates".to_string(),
                document_ids: vec![],
                magnitude: ChangeMagnitude::Minor,
            },
        ];
        
        self.changes.insert(newer.time, changes);
        Ok(())
    }
    
    pub fn compute_activity_buckets(&mut self) {
        // Create hourly buckets
        let bucket_size_ms = 3600000; // 1 hour
        
        if let (Some(start), Some(end)) = (self.snapshots.keys().next(), self.snapshots.keys().last()) {
            let start_ms = start.timestamp_millis();
            let end_ms = end.timestamp_millis();
            
            let mut current = start_ms;
            while current < end_ms {
                let bucket_end = current + bucket_size_ms;
                let change_count = self.changes
                    .range(*start..*end)
                    .map(|(_, changes)| changes.len())
                    .sum();
                
                self.activity_buckets.push(ActivityBucket {
                    start: current,
                    end: bucket_end,
                    change_count,
                });
                
                current = bucket_end;
            }
        }
    }
}

/// Service for reconstructing document state at any point in time
pub struct StateReconstructor {
    index: Arc<RwLock<TimelineIndex>>,
    snapshot_mgr: Arc<SnapshotManager>,
    cache: Arc<RwLock<StateCache>>,
}

pub struct StateCache {
    pub entries: HashMap<DateTime<Utc>, CachedState>,
    pub max_size: usize,
}

struct CachedState {
    timestamp: DateTime<Utc>,
    document_count: usize,
    folder_structure: serde_json::Value,
}

impl StateReconstructor {
    pub fn new(index: Arc<RwLock<TimelineIndex>>, snapshot_mgr: Arc<SnapshotManager>) -> Self {
        Self {
            index,
            snapshot_mgr,
            cache: Arc::new(RwLock::new(StateCache {
                entries: HashMap::new(),
                max_size: 100,
            })),
        }
    }
    
    /// Get document state at specific timestamp
    pub async fn get_state_at(&self, timestamp: DateTime<Utc>) -> anyhow::Result<DocumentState> {
        // Check cache first
        {
            let cache = self.cache.read().await;
            if let Some(cached) = cache.entries.get(&timestamp) {
                return Ok(DocumentState {
                    timestamp,
                    document_count: cached.document_count,
                    folder_structure: cached.folder_structure.clone(),
                    nearest_snapshot: None,
                    recent_changes: vec![],
                });
            }
        }
        
        // Find nearest snapshot
        let index = self.index.read().await;
        let nearest = index.find_nearest_snapshot(timestamp)
            .ok_or_else(|| anyhow::anyhow!("No snapshot found before timestamp"))?;
        
        // Load snapshot state into a temporary store
        let temp_path = format!("/tmp/timeline_temp_{}", uuid::Uuid::new_v4());
        let mut store = DocumentStore::new(&temp_path)?;
        self.snapshot_mgr.restore(&mut store, &nearest.id)?;
        
        // Apply changes since snapshot
        let changes = index.get_changes_between(nearest.timestamp, timestamp);
        
        let state = DocumentState {
            timestamp,
            document_count: store.iter().count(),
            folder_structure: self.build_folder_structure(&store)?,
            nearest_snapshot: Some(NearestSnapshot {
                id: nearest.id.clone(),
                timestamp: nearest.timestamp,
                offset_ms: (nearest.timestamp - timestamp).num_milliseconds(),
            }),
            recent_changes: changes.into_iter().cloned().collect(),
        };
        
        // Cache result
        {
            let mut cache = self.cache.write().await;
            if cache.entries.len() >= cache.max_size {
                // Simple eviction - remove oldest
                if let Some(oldest) = cache.entries.keys().min().cloned() {
                    cache.entries.remove(&oldest);
                }
            }
            cache.entries.insert(timestamp, CachedState {
                timestamp,
                document_count: state.document_count,
                folder_structure: state.folder_structure.clone(),
            });
        }
        
        Ok(state)
    }
    
    fn build_folder_structure(&self, _store: &DocumentStore) -> anyhow::Result<serde_json::Value> {
        // Build hierarchical folder structure from documents
        Ok(serde_json::json!({
            "root": {
                "id": "root",
                "children": []
            }
        }))
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DocumentState {
    pub timestamp: DateTime<Utc>,
    pub document_count: usize,
    pub folder_structure: serde_json::Value,
    pub nearest_snapshot: Option<NearestSnapshot>,
    pub recent_changes: Vec<TimelineChange>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct NearestSnapshot {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub offset_ms: i64,
}

/// State for timeline handlers
#[derive(Clone)]
pub struct TimelineState {
    pub index: Arc<RwLock<TimelineIndex>>,
    pub reconstructor: Arc<StateReconstructor>,
    pub snapshot_mgr: Arc<SnapshotManager>,
}

#[derive(Serialize, Deserialize)]
pub struct TimelineInfo {
    pub start_time: DateTime<Utc>,
    pub end_time: DateTime<Utc>,
    pub total_duration_ms: i64,
    pub snapshot_count: usize,
    pub change_density: ChangeDensity,
}

#[derive(Serialize, Deserialize)]
pub struct ChangeDensity {
    pub buckets: Vec<ActivityBucket>,
    pub bucket_size_ms: i64,
}