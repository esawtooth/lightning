use axum::{routing::get, serve, Router};
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio::time::Duration;
use tokio::task::LocalSet;
use std::future::IntoFuture;

mod api;
mod snapshot;
mod storage;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // initialize snapshot repository for durability
    let snapshot_mgr = Arc::new(snapshot::SnapshotManager::new("snapshots")?);

    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new("data")?));
    let router = api::router(store.clone());
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
