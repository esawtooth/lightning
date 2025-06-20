#[cfg(test)]
mod tests {
    use crate::timeline::*;
    use crate::snapshot::SnapshotManager;
    use crate::storage::crdt::{DocumentStore, DocumentType};
    use chrono::{DateTime, Utc, TimeZone};
    use tempfile::TempDir;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tokio::sync::RwLock;
    use uuid::Uuid;

    fn create_test_timestamp(secs: i64) -> DateTime<Utc> {
        Utc.timestamp_opt(secs, 0).unwrap()
    }

    #[test]
    fn test_timeline_index_new() {
        let index = TimelineIndex::new();
        assert!(index.snapshots.is_empty());
        assert!(index.changes.is_empty());
        assert!(index.document_lifecycles.is_empty());
        assert!(index.activity_buckets.is_empty());
    }

    #[test]
    fn test_find_nearest_snapshot() {
        let mut index = TimelineIndex::new();
        
        // Add some snapshots
        let snap1 = SnapshotRef {
            id: "snap1".to_string(),
            timestamp: create_test_timestamp(1000),
            document_count: 10,
        };
        let snap2 = SnapshotRef {
            id: "snap2".to_string(),
            timestamp: create_test_timestamp(2000),
            document_count: 15,
        };
        let snap3 = SnapshotRef {
            id: "snap3".to_string(),
            timestamp: create_test_timestamp(3000),
            document_count: 20,
        };
        
        index.snapshots.insert(snap1.timestamp, snap1.clone());
        index.snapshots.insert(snap2.timestamp, snap2.clone());
        index.snapshots.insert(snap3.timestamp, snap3.clone());
        
        // Test finding nearest snapshots
        assert_eq!(
            index.find_nearest_snapshot(create_test_timestamp(500)),
            None
        );
        assert_eq!(
            index.find_nearest_snapshot(create_test_timestamp(1500)).unwrap().id,
            "snap1"
        );
        assert_eq!(
            index.find_nearest_snapshot(create_test_timestamp(2500)).unwrap().id,
            "snap2"
        );
        assert_eq!(
            index.find_nearest_snapshot(create_test_timestamp(3500)).unwrap().id,
            "snap3"
        );
    }

    #[test]
    fn test_get_changes_between() {
        let mut index = TimelineIndex::new();
        
        // Add changes at different timestamps
        let change1 = TimelineChange {
            timestamp: create_test_timestamp(1500),
            offset_ms: 1500000,
            change_type: ChangeType::DocumentCreated,
            summary: "Created doc1".to_string(),
            document_ids: vec![Uuid::new_v4()],
            magnitude: ChangeMagnitude::Minor,
        };
        let change2 = TimelineChange {
            timestamp: create_test_timestamp(2500),
            offset_ms: 2500000,
            change_type: ChangeType::DocumentModified,
            summary: "Modified doc2".to_string(),
            document_ids: vec![Uuid::new_v4()],
            magnitude: ChangeMagnitude::Minor,
        };
        let change3 = TimelineChange {
            timestamp: create_test_timestamp(3500),
            offset_ms: 3500000,
            change_type: ChangeType::BulkUpdate,
            summary: "Bulk update".to_string(),
            document_ids: vec![Uuid::new_v4(); 5],
            magnitude: ChangeMagnitude::Major,
        };
        
        index.changes.insert(change1.timestamp, vec![change1.clone()]);
        index.changes.insert(change2.timestamp, vec![change2.clone()]);
        index.changes.insert(change3.timestamp, vec![change3.clone()]);
        
        // Test range queries
        let changes = index.get_changes_between(
            create_test_timestamp(1000),
            create_test_timestamp(2000)
        );
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].summary, "Created doc1");
        
        let changes = index.get_changes_between(
            create_test_timestamp(2000),
            create_test_timestamp(4000)
        );
        assert_eq!(changes.len(), 2);
        
        let changes = index.get_changes_between(
            create_test_timestamp(1000),
            create_test_timestamp(4000)
        );
        assert_eq!(changes.len(), 3);
    }

    #[test]
    fn test_change_magnitude_classification() {
        // Test that change magnitudes are properly classified
        let minor_change = TimelineChange {
            timestamp: create_test_timestamp(1000),
            offset_ms: 1000000,
            change_type: ChangeType::DocumentCreated,
            summary: "Single doc".to_string(),
            document_ids: vec![Uuid::new_v4()],
            magnitude: ChangeMagnitude::Minor,
        };
        
        let moderate_change = TimelineChange {
            timestamp: create_test_timestamp(2000),
            offset_ms: 2000000,
            change_type: ChangeType::BulkUpdate,
            summary: "Several docs".to_string(),
            document_ids: vec![Uuid::new_v4(); 5],
            magnitude: ChangeMagnitude::Moderate,
        };
        
        let major_change = TimelineChange {
            timestamp: create_test_timestamp(3000),
            offset_ms: 3000000,
            change_type: ChangeType::BulkUpdate,
            summary: "Many docs".to_string(),
            document_ids: vec![Uuid::new_v4(); 15],
            magnitude: ChangeMagnitude::Major,
        };
        
        assert!(matches!(minor_change.magnitude, ChangeMagnitude::Minor));
        assert!(matches!(moderate_change.magnitude, ChangeMagnitude::Moderate));
        assert!(matches!(major_change.magnitude, ChangeMagnitude::Major));
    }

    #[test]
    fn test_activity_buckets() {
        let mut index = TimelineIndex::new();
        
        // Add snapshots to define timeline range
        index.snapshots.insert(
            create_test_timestamp(0),
            SnapshotRef {
                id: "start".to_string(),
                timestamp: create_test_timestamp(0),
                document_count: 0,
            }
        );
        index.snapshots.insert(
            create_test_timestamp(7200), // 2 hours later
            SnapshotRef {
                id: "end".to_string(),
                timestamp: create_test_timestamp(7200),
                document_count: 10,
            }
        );
        
        // Add changes
        index.changes.insert(create_test_timestamp(1800), vec![
            TimelineChange {
                timestamp: create_test_timestamp(1800),
                offset_ms: 1800000,
                change_type: ChangeType::DocumentCreated,
                summary: "Change 1".to_string(),
                document_ids: vec![Uuid::new_v4()],
                magnitude: ChangeMagnitude::Minor,
            }
        ]);
        
        index.compute_activity_buckets();
        
        // Should have 2 hourly buckets
        assert_eq!(index.activity_buckets.len(), 2);
        assert_eq!(index.activity_buckets[0].start, 0);
        assert_eq!(index.activity_buckets[0].end, 3600000);
        assert_eq!(index.activity_buckets[1].start, 3600000);
        assert_eq!(index.activity_buckets[1].end, 7200000);
    }

    #[tokio::test]
    async fn test_state_reconstruction() {
        let temp_dir = TempDir::new().unwrap();
        let snapshot_dir = temp_dir.path().join("snapshots");
        let data_dir = temp_dir.path().join("data");
        
        std::fs::create_dir_all(&snapshot_dir).unwrap();
        std::fs::create_dir_all(&data_dir).unwrap();
        
        // Create test snapshot manager and document store
        let snapshot_mgr = Arc::new(SnapshotManager::new(&snapshot_dir).unwrap());
        let mut store = DocumentStore::new(&data_dir).unwrap();
        
        // Add test documents
        let _doc_id = store.create(
            "Test Document".to_string(),
            "Test content",
            "test_user".to_string(),
            None,
            DocumentType::Text,
        ).unwrap();
        
        // Take snapshot
        let snapshot_id = snapshot_mgr.snapshot(&store).unwrap();
        
        // Create timeline index
        let index = Arc::new(RwLock::new(TimelineIndex::new()));
        let reconstructor = StateReconstructor::new(index.clone(), snapshot_mgr.clone());
        
        // Add snapshot to index
        {
            let mut idx = index.write().await;
            idx.snapshots.insert(
                Utc::now(),
                SnapshotRef {
                    id: snapshot_id.to_string(),
                    timestamp: Utc::now(),
                    document_count: 1,
                }
            );
        }
        
        // Test state reconstruction
        let state = reconstructor.get_state_at(Utc::now()).await.unwrap();
        assert_eq!(state.document_count, 1);
        assert!(state.nearest_snapshot.is_some());
    }

    #[test]
    fn test_document_lifecycle() {
        let mut index = TimelineIndex::new();
        let doc_id = Uuid::new_v4();
        
        let lifecycle = DocumentLifecycle {
            document_id: doc_id,
            events: vec![
                LifecycleEvent {
                    timestamp: create_test_timestamp(1000),
                    event_type: LifecycleEventType::Created,
                    offset_ms: 1000000,
                },
                LifecycleEvent {
                    timestamp: create_test_timestamp(2000),
                    event_type: LifecycleEventType::Modified,
                    offset_ms: 2000000,
                },
                LifecycleEvent {
                    timestamp: create_test_timestamp(3000),
                    event_type: LifecycleEventType::Deleted,
                    offset_ms: 3000000,
                },
            ],
        };
        
        index.document_lifecycles.insert(doc_id, lifecycle.clone());
        
        let retrieved = index.document_lifecycles.get(&doc_id).unwrap();
        assert_eq!(retrieved.events.len(), 3);
        assert!(matches!(retrieved.events[0].event_type, LifecycleEventType::Created));
        assert!(matches!(retrieved.events[1].event_type, LifecycleEventType::Modified));
        assert!(matches!(retrieved.events[2].event_type, LifecycleEventType::Deleted));
    }

    #[test]
    fn test_timeline_info_serialization() {
        let info = TimelineInfo {
            start_time: create_test_timestamp(1000),
            end_time: create_test_timestamp(5000),
            total_duration_ms: 4000000,
            snapshot_count: 5,
            change_density: ChangeDensity {
                buckets: vec![
                    ActivityBucket {
                        start: 0,
                        end: 3600000,
                        change_count: 10,
                    }
                ],
                bucket_size_ms: 3600000,
            },
        };
        
        let json = serde_json::to_string(&info).unwrap();
        let deserialized: TimelineInfo = serde_json::from_str(&json).unwrap();
        
        assert_eq!(deserialized.snapshot_count, 5);
        assert_eq!(deserialized.total_duration_ms, 4000000);
        assert_eq!(deserialized.change_density.buckets.len(), 1);
    }

    #[test]
    fn test_state_cache() {
        let cache = StateCache {
            entries: HashMap::new(),
            max_size: 2,
        };
        
        assert_eq!(cache.entries.len(), 0);
        assert_eq!(cache.max_size, 2);
    }
}