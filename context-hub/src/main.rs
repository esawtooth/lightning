use context_hub_core::{
    auth,
    events,
    indexer,
    pointer::BlobPointerResolver,
    search,
    snapshot,
    storage,
};
use axum::{routing::get, serve, Router};
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
    {
        let mut guard = store.write().await;
        let blob_resolver = Arc::new(BlobPointerResolver::new(&blob_dir)?);
        guard.register_resolver("blob", blob_resolver);
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
        .and_then(|v| v.parse::<usize>().ok());
    let router = api::router(
        store.clone(),
        PathBuf::from(&snapshot_dir),
        snapshot_retention,
        indexer.clone(),
        events.clone(),
        verifier,
    );
    // spawn periodic snapshots every hour on a LocalSet so non-Send types work
    let local = LocalSet::new();
    let interval = std::env::var("SNAPSHOT_INTERVAL_SECS")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(3600);
    local.spawn_local(snapshot::snapshot_task(
        store.clone(),
        snapshot_mgr.clone(),
        Duration::from_secs(interval),
        snapshot_retention,
    ));
    let app = Router::new().merge(router).route("/health", get(|| async {
        axum::Json(serde_json::json!({
            "status": "healthy",
            "service": "context-hub",
            "timestamp": chrono::Utc::now().to_rfc3339()
        }))
    }));

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
