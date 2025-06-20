use context_hub_core::{
    timeline::{TimelineIndex, TimelineChange, ChangeType, ChangeMagnitude},
    storage::crdt::{DocumentStore, DocumentType},
    snapshot::SnapshotManager,
};
use chrono::{DateTime, Utc, TimeZone};
use tempfile::TempDir;
use uuid::Uuid;

#[tokio::test]
async fn test_timeline_basic_functionality() {
    let temp_dir = TempDir::new().unwrap();
    let data_dir = temp_dir.path().join("data");
    let snapshot_dir = temp_dir.path().join("snapshots");
    
    std::fs::create_dir_all(&data_dir).unwrap();
    std::fs::create_dir_all(&snapshot_dir).unwrap();
    
    // Create document store and add documents
    let mut store = DocumentStore::new(&data_dir).unwrap();
    let doc1 = store.create(
        "Test Doc 1".to_string(),
        "Content 1",
        "test_user".to_string(),
        None,
        DocumentType::Text,
    ).unwrap();
    
    // Create snapshot manager and take snapshot
    let snapshot_mgr = SnapshotManager::new(&snapshot_dir).unwrap();
    let snapshot_id = snapshot_mgr.snapshot(&store).unwrap();
    
    // Create timeline index
    let mut index = TimelineIndex::new();
    assert!(index.snapshots.is_empty());
    
    // Test adding snapshot reference
    let now = Utc::now();
    index.snapshots.insert(now, context_hub_core::timeline::SnapshotRef {
        id: snapshot_id.to_string(),
        timestamp: now,
        document_count: 1,
    });
    
    assert_eq!(index.snapshots.len(), 1);
    
    // Test finding nearest snapshot
    let found = index.find_nearest_snapshot(now);
    assert!(found.is_some());
    assert_eq!(found.unwrap().document_count, 1);
    
    // Test adding changes
    let change = TimelineChange {
        timestamp: now,
        offset_ms: now.timestamp_millis(),
        change_type: ChangeType::DocumentCreated,
        summary: "Created test document".to_string(),
        document_ids: vec![doc1],
        magnitude: ChangeMagnitude::Minor,
    };
    
    index.changes.insert(now, vec![change]);
    assert_eq!(index.changes.len(), 1);
    
    // Test getting changes between timestamps
    let past = now - chrono::Duration::hours(1);
    let future = now + chrono::Duration::hours(1);
    let changes = index.get_changes_between(past, future);
    assert_eq!(changes.len(), 1);
}

#[test]
fn test_timeline_change_serialization() {
    let change = TimelineChange {
        timestamp: Utc.timestamp_opt(1640995200, 0).unwrap(),
        offset_ms: 1640995200000,
        change_type: ChangeType::DocumentModified,
        summary: "Test change".to_string(),
        document_ids: vec![Uuid::new_v4()],
        magnitude: ChangeMagnitude::Minor,
    };
    
    let json = serde_json::to_string(&change).unwrap();
    let deserialized: TimelineChange = serde_json::from_str(&json).unwrap();
    
    assert_eq!(change.summary, deserialized.summary);
    assert!(matches!(deserialized.change_type, ChangeType::DocumentModified));
    assert!(matches!(deserialized.magnitude, ChangeMagnitude::Minor));
}

#[test]
fn test_activity_buckets() {
    let mut index = TimelineIndex::new();
    
    // Add snapshots to define range
    let start_time = Utc.timestamp_opt(0, 0).unwrap();
    let end_time = Utc.timestamp_opt(7200, 0).unwrap(); // 2 hours
    
    index.snapshots.insert(start_time, context_hub_core::timeline::SnapshotRef {
        id: "start".to_string(),
        timestamp: start_time,
        document_count: 0,
    });
    
    index.snapshots.insert(end_time, context_hub_core::timeline::SnapshotRef {
        id: "end".to_string(),
        timestamp: end_time,
        document_count: 10,
    });
    
    // Add some changes
    let mid_time = Utc.timestamp_opt(1800, 0).unwrap(); // 30 min
    let change = TimelineChange {
        timestamp: mid_time,
        offset_ms: 1800000,
        change_type: ChangeType::DocumentCreated,
        summary: "Mid change".to_string(),
        document_ids: vec![Uuid::new_v4()],
        magnitude: ChangeMagnitude::Minor,
    };
    
    index.changes.insert(mid_time, vec![change]);
    
    // Compute activity buckets
    index.compute_activity_buckets();
    
    // Should have 2 hourly buckets
    assert_eq!(index.activity_buckets.len(), 2);
}