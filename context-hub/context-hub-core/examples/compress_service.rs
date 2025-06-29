//! Example of how to use the new CompressService instead of the deprecated snapshot_task

use anyhow::Result;
use context_hub_core::{
    pointer::BlobPointerResolver,
    search::SearchIndex,
    services::compress::{compress_monitor_task, CompressConfig, CompressService},
    snapshot::SnapshotManager,
    storage::crdt::DocumentStore,
    wal::WriteAheadLog,
};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize components
    let data_dir = "/tmp/context-hub/data";
    let index_dir = "/tmp/context-hub/index";
    let wal_dir = "/tmp/context-hub/wal";
    let blob_dir = "/tmp/context-hub/blobs";
    let snapshot_dir = "/tmp/context-hub/snapshots";

    // Create document store
    let store = Arc::new(RwLock::new(DocumentStore::new(data_dir)?));

    // Create snapshot manager
    let snapshot_manager = Arc::new(SnapshotManager::new(snapshot_dir)?);

    // Create optional components
    let search_index = Arc::new(SearchIndex::new(index_dir)?);
    let wal = Arc::new(WriteAheadLog::new(wal_dir).await?);
    let blob_resolver = Arc::new(BlobPointerResolver::new(blob_dir)?);

    // Configure compression
    let config = CompressConfig {
        threshold_percent: 100.0,        // Compress when storage doubles
        min_interval_secs: 300,          // At least 5 minutes between compressions
        max_interval_secs: 86400,        // Force compress every 24 hours
        snapshot_retention: 10,          // Keep 10 snapshots
        enable_wal_compact: true,
        enable_blob_cleanup: true,
        enable_index_optimize: true,
    };

    // Create compress service
    let compress_service = Arc::new(
        CompressService::new(
            store.clone(),
            snapshot_manager,
            data_dir,
            index_dir,
            wal_dir,
            config,
        )
        .with_search_index(search_index)
        .with_wal(wal)
        .with_blob_resolver(blob_resolver),
    );

    // Option 1: Manual compression
    println!("Performing manual compression...");
    match compress_service.compress().await {
        Ok(stats) => {
            println!("Compression completed:");
            println!("  - Storage before: {} bytes", stats.storage_before);
            println!("  - Storage after: {} bytes", stats.storage_after);
            println!("  - Bytes freed: {}", stats.bytes_freed);
            println!("  - Duration: {:.2}s", stats.duration_secs);
        }
        Err(e) => eprintln!("Compression failed: {}", e),
    }

    // Option 2: Spawn background monitor task (using LocalSet for git2 thread safety)
    println!("Starting background compression monitor...");
    let local = tokio::task::LocalSet::new();
    local.spawn_local(compress_monitor_task(
        compress_service.clone(),
        Duration::from_secs(60), // Check every minute
    ));

    // Option 3: Check if compression is needed
    if compress_service.should_compress().await? {
        println!("Storage threshold exceeded, compression recommended");
    }

    // Keep the example running for a short time to see the monitor in action
    local.run_until(async {
        tokio::time::sleep(Duration::from_secs(10)).await;
    }).await;

    Ok(())
}

// Migration guide from old code to new:
//
// OLD CODE:
// ```rust
// use snapshot::snapshot_task;
// 
// let interval = Duration::from_secs(3600);
// tokio::spawn(snapshot_task(
//     store.clone(),
//     snapshot_mgr.clone(),
//     interval,
//     Some(10),
// ));
// ```
//
// NEW CODE:
// ```rust
// use services::compress::{CompressService, compress_monitor_task, CompressConfig};
// 
// let compress_service = Arc::new(
//     CompressService::new(
//         store.clone(),
//         snapshot_mgr.clone(),
//         data_dir,
//         index_dir,
//         wal_dir,
//         CompressConfig::default(),
//     )
//     .with_search_index(search_index)
//     .with_wal(wal)
//     .with_blob_resolver(blob_resolver),
// );
// 
// tokio::spawn(compress_monitor_task(
//     compress_service,
//     Duration::from_secs(60), // Check interval (not snapshot interval)
// ));
// ```