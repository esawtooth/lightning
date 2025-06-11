use axum::{routing::get, serve, Router};
use std::future::IntoFuture;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio::task::LocalSet;
use tokio::time::Duration;

mod api;
mod search;
mod snapshot;
mod storage;
mod indexer;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // initialize snapshot repository for durability
    let snapshot_mgr = Arc::new(snapshot::SnapshotManager::new("snapshots")?);

    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new("data")?));
    let search = Arc::new(search::SearchIndex::new("index")?);
    {
        let store_guard = store.lock().await;
        search.index_all(&store_guard)?;
    }
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let router = api::router(store.clone(), PathBuf::from("snapshots"), indexer.clone());
    // spawn periodic snapshots every hour on a LocalSet so non-Send types work
    let local = LocalSet::new();
    local.spawn_local(snapshot::snapshot_task(
        store.clone(),
        snapshot_mgr.clone(),
        Duration::from_secs(3600),
    ));
    let app = Router::new()
        .merge(router)
        .route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:3000").await?;
    println!("Listening on 127.0.0.1:3000");
    local
        .run_until(serve(listener, app.into_make_service()).into_future())
        .await?;
    Ok(())
}
