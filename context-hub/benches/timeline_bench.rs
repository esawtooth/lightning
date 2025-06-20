use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use context_hub_core::{
    timeline::{TimelineIndex, StateReconstructor, TimelineChange, ChangeType, ChangeMagnitude},
    snapshot::SnapshotManager,
    storage::crdt::DocumentStore,
};
use chrono::{DateTime, Utc, TimeZone};
use std::sync::Arc;
use tokio::sync::RwLock;
use tempfile::TempDir;
use uuid::Uuid;

fn create_test_timestamp(secs: i64) -> DateTime<Utc> {
    Utc.timestamp_opt(secs, 0).unwrap()
}

fn setup_timeline_index(num_snapshots: usize, changes_per_snapshot: usize) -> TimelineIndex {
    let mut index = TimelineIndex::new();
    
    // Add snapshots
    for i in 0..num_snapshots {
        let timestamp = create_test_timestamp((i * 3600) as i64); // Hourly snapshots
        index.snapshots.insert(
            timestamp,
            context_hub_core::timeline::SnapshotRef {
                id: format!("snapshot_{}", i),
                timestamp,
                document_count: i * 10,
            }
        );
        
        // Add changes for each snapshot
        let mut changes = Vec::new();
        for j in 0..changes_per_snapshot {
            changes.push(TimelineChange {
                timestamp: timestamp + chrono::Duration::minutes(j as i64),
                offset_ms: 0,
                change_type: ChangeType::DocumentModified,
                summary: format!("Change {} for snapshot {}", j, i),
                document_ids: vec![Uuid::new_v4()],
                magnitude: ChangeMagnitude::Minor,
            });
        }
        
        if !changes.is_empty() {
            index.changes.insert(timestamp, changes);
        }
    }
    
    index
}

fn bench_find_nearest_snapshot(c: &mut Criterion) {
    let mut group = c.benchmark_group("find_nearest_snapshot");
    
    for size in [10, 100, 1000].iter() {
        let index = setup_timeline_index(*size, 5);
        
        group.bench_with_input(
            BenchmarkId::new("snapshots", size),
            size,
            |b, _| {
                b.iter(|| {
                    // Search for timestamp in the middle
                    let search_time = create_test_timestamp((size * 3600 / 2) as i64);
                    index.find_nearest_snapshot(black_box(search_time))
                });
            },
        );
    }
    
    group.finish();
}

fn bench_get_changes_between(c: &mut Criterion) {
    let mut group = c.benchmark_group("get_changes_between");
    
    for changes_per_snapshot in [10, 50, 100].iter() {
        let index = setup_timeline_index(100, *changes_per_snapshot);
        
        group.bench_with_input(
            BenchmarkId::new("changes_per_snapshot", changes_per_snapshot),
            changes_per_snapshot,
            |b, _| {
                b.iter(|| {
                    let start = create_test_timestamp(0);
                    let end = create_test_timestamp(360000); // 100 hours
                    index.get_changes_between(black_box(start), black_box(end))
                });
            },
        );
    }
    
    group.finish();
}

fn bench_timeline_index_build(c: &mut Criterion) {
    let mut group = c.benchmark_group("timeline_index_build");
    
    let temp_dir = TempDir::new().unwrap();
    let snapshot_dir = temp_dir.path().join("snapshots");
    let data_dir = temp_dir.path().join("data");
    
    std::fs::create_dir_all(&snapshot_dir).unwrap();
    std::fs::create_dir_all(&data_dir).unwrap();
    
    let snapshot_mgr = SnapshotManager::new(&snapshot_dir).unwrap();
    let mut store = DocumentStore::new(&data_dir).unwrap();
    
    // Create some snapshots
    for i in 0..10 {
        let doc_id = Uuid::new_v4();
        store.create(
            doc_id,
            "bench_user",
            &format!("Doc {}", i),
            &format!("Content {}", i),
            None,
            context_hub_core::storage::crdt::DocumentType::Document,
        ).unwrap();
        snapshot_mgr.snapshot(&store).unwrap();
    }
    
    group.bench_function("build_from_10_snapshots", |b| {
        b.iter(|| {
            let mut index = TimelineIndex::new();
            let runtime = tokio::runtime::Runtime::new().unwrap();
            runtime.block_on(async {
                index.build_from_snapshots(&snapshot_mgr).await.unwrap();
            });
        });
    });
    
    group.finish();
}

fn bench_state_reconstruction(c: &mut Criterion) {
    let mut group = c.benchmark_group("state_reconstruction");
    
    let temp_dir = TempDir::new().unwrap();
    let snapshot_dir = temp_dir.path().join("snapshots");
    let data_dir = temp_dir.path().join("data");
    
    std::fs::create_dir_all(&snapshot_dir).unwrap();
    std::fs::create_dir_all(&data_dir).unwrap();
    
    let snapshot_mgr = Arc::new(SnapshotManager::new(&snapshot_dir).unwrap());
    let mut store = DocumentStore::new(&data_dir).unwrap();
    
    // Create a snapshot with documents
    for i in 0..100 {
        let doc_id = Uuid::new_v4();
        store.create(
            doc_id,
            "bench_user",
            &format!("Doc {}", i),
            &format!("Content {}", i),
            None,
            context_hub_core::storage::crdt::DocumentType::Document,
        ).unwrap();
    }
    let snapshot_id = snapshot_mgr.snapshot(&store).unwrap();
    
    let runtime = tokio::runtime::Runtime::new().unwrap();
    
    runtime.block_on(async {
        let index = Arc::new(RwLock::new(TimelineIndex::new()));
        
        // Add snapshot to index
        {
            let mut idx = index.write().await;
            idx.snapshots.insert(
                Utc::now(),
                context_hub_core::timeline::SnapshotRef {
                    id: snapshot_id.to_string(),
                    timestamp: Utc::now(),
                    document_count: 100,
                }
            );
        }
        
        let reconstructor = StateReconstructor::new(index.clone(), snapshot_mgr.clone());
        
        group.bench_function("reconstruct_100_docs", |b| {
            b.iter(|| {
                runtime.block_on(async {
                    reconstructor.get_state_at(black_box(Utc::now())).await.unwrap()
                })
            });
        });
    });
    
    group.finish();
}

fn bench_activity_buckets(c: &mut Criterion) {
    let mut group = c.benchmark_group("activity_buckets");
    
    for num_changes in [100, 1000, 10000].iter() {
        let mut index = TimelineIndex::new();
        
        // Add snapshots to define range
        index.snapshots.insert(
            create_test_timestamp(0),
            context_hub_core::timeline::SnapshotRef {
                id: "start".to_string(),
                timestamp: create_test_timestamp(0),
                document_count: 0,
            }
        );
        index.snapshots.insert(
            create_test_timestamp(86400), // 24 hours
            context_hub_core::timeline::SnapshotRef {
                id: "end".to_string(),
                timestamp: create_test_timestamp(86400),
                document_count: 1000,
            }
        );
        
        // Add changes throughout the day
        for i in 0..*num_changes {
            let timestamp = create_test_timestamp((i * 86400 / num_changes) as i64);
            index.changes.insert(timestamp, vec![
                TimelineChange {
                    timestamp,
                    offset_ms: 0,
                    change_type: ChangeType::DocumentModified,
                    summary: format!("Change {}", i),
                    document_ids: vec![Uuid::new_v4()],
                    magnitude: ChangeMagnitude::Minor,
                }
            ]);
        }
        
        group.bench_with_input(
            BenchmarkId::new("changes", num_changes),
            num_changes,
            |b, _| {
                b.iter(|| {
                    index.compute_activity_buckets();
                });
            },
        );
    }
    
    group.finish();
}

criterion_group!(
    benches,
    bench_find_nearest_snapshot,
    bench_get_changes_between,
    bench_timeline_index_build,
    bench_state_reconstruction,
    bench_activity_buckets
);
criterion_main!(benches);