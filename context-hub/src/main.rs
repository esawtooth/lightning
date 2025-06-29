use context_hub_core::{
    auth,
    events,
    indexer,
    pointer::BlobPointerResolver,
    search,
    services::compress::{compress_monitor_task, CompressConfig, CompressService},
    snapshot,
    storage,
};
use axum::{serve, Router};
use std::future::IntoFuture;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::RwLock;
use tokio::task::LocalSet;
use tokio::time::Duration;

mod api;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let data_dir = std::env::var("DATA_DIR").unwrap_or_else(|_| "data".into());
    let snapshot_dir = std::env::var("SNAPSHOT_DIR").unwrap_or_else(|_| "snapshots".into());
    let index_dir = std::env::var("INDEX_DIR").unwrap_or_else(|_| "index".into());
    let blob_dir = std::env::var("BLOB_DIR").unwrap_or_else(|_| "blobs".into());

    // initialize snapshot repository for durability
    let snapshot_mgr = Arc::new(snapshot::SnapshotManager::new(&snapshot_dir)?);

    let store = Arc::new(RwLock::new(storage::crdt::DocumentStore::new(&data_dir)?));
    let search = Arc::new(search::SearchIndex::new(&index_dir)?);
    let blob_resolver = Arc::new(BlobPointerResolver::new(&blob_dir)?);
    {
        let mut guard = store.write().await;
        guard.register_resolver("blob", blob_resolver.clone());
    }
    {
        let store_guard = store.read().await;
        search.index_all(&store_guard)?;
    }
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = events::EventBus::new();
    let verifier: Arc<dyn auth::TokenVerifier> = if let Ok(url) = std::env::var("AZURE_JWKS_URL") {
        Arc::new(auth::legacy::AzureEntraIdVerifier::new(url))
    } else {
        let secret = std::env::var("JWT_SECRET").unwrap_or_else(|_| "secret".to_string());
        Arc::new(auth::legacy::Hs256Verifier::new(secret))
    };
    let snapshot_retention = std::env::var("SNAPSHOT_RETENTION")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(10);
    
    // Create the compress service
    let compress_config = CompressConfig {
        threshold_percent: std::env::var("COMPRESS_THRESHOLD_PERCENT")
            .ok()
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(100.0),
        min_interval_secs: std::env::var("COMPRESS_MIN_INTERVAL_SECS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(300),
        max_interval_secs: std::env::var("COMPRESS_MAX_INTERVAL_SECS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(86400),
        snapshot_retention,
        enable_wal_compact: false, // WAL not initialized in this example
        enable_blob_cleanup: true,
        enable_index_optimize: true,
    };
    
    let compress_service = Arc::new(
        CompressService::new(
            store.clone(),
            snapshot_mgr.clone(),
            &data_dir,
            &index_dir,
            &data_dir, // Using data_dir as WAL dir for now
            compress_config,
        )
        .with_search_index(search.clone())
        .with_blob_resolver(blob_resolver),
    );
    
    let router = api::router(
        store.clone(),
        PathBuf::from(&snapshot_dir),
        Some(snapshot_retention),
        indexer.clone(),
        events.clone(),
        verifier,
    );
    
    // Spawn the compress monitor task instead of the old snapshot task
    let local = LocalSet::new();
    let check_interval = std::env::var("COMPRESS_CHECK_INTERVAL_SECS")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(60); // Check every minute
    local.spawn_local(compress_monitor_task(
        compress_service,
        Duration::from_secs(check_interval),
    ));
    let app = Router::new().merge(router);

    let host = std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into());
    let port = std::env::var("PORT").unwrap_or_else(|_| "3000".into());
    let addr = format!("{}:{}", host, port);
    let listener = TcpListener::bind(&addr).await?;
    println!("Listening on {}", addr);
    local
        .run_until(serve(listener, app.into_make_service()).into_future())
        .await?;
    Ok(())
}
