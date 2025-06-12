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
use tokio::sync::Mutex;
use tokio::task::LocalSet;
use tokio::time::Duration;

mod api;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // initialize snapshot repository for durability
    let snapshot_mgr = Arc::new(snapshot::SnapshotManager::new("snapshots")?);

    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new("data")?));
    let search = Arc::new(search::SearchIndex::new("index")?);
    {
        let mut guard = store.lock().await;
        let blob_resolver = Arc::new(BlobPointerResolver::new("blobs")?);
        guard.register_resolver("blob", blob_resolver);
    }
    {
        let store_guard = store.lock().await;
        search.index_all(&store_guard)?;
    }
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = events::EventBus::new();
    let verifier: Arc<dyn auth::TokenVerifier> = if let Ok(url) = std::env::var("AZURE_JWKS_URL") {
        Arc::new(auth::AzureEntraIdVerifier::new(url))
    } else {
        let secret = std::env::var("JWT_SECRET").unwrap_or_else(|_| "secret".to_string());
        Arc::new(auth::Hs256Verifier::new(secret))
    };
    let router = api::router(
        store.clone(),
        PathBuf::from("snapshots"),
        indexer.clone(),
        events.clone(),
        verifier,
    );
    // spawn periodic snapshots every hour on a LocalSet so non-Send types work
    let local = LocalSet::new();
    local.spawn_local(snapshot::snapshot_task(
        store.clone(),
        snapshot_mgr.clone(),
        Duration::from_secs(3600),
    ));
    let app = Router::new().merge(router).route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:3000").await?;
    println!("Listening on 127.0.0.1:3000");
    local
        .run_until(serve(listener, app.into_make_service()).into_future())
        .await?;
    Ok(())
}
