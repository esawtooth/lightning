use axum::{routing::get, serve, Router};
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::Mutex;

mod api;
mod storage;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let store = storage::crdt::DocumentStore::new("data")?;
    let router = api::router(Arc::new(Mutex::new(store)));
    let app = Router::new()
        .merge(router)
        .route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:3000").await?;
    println!("Listening on 127.0.0.1:3000");
    serve(listener, app.into_make_service()).await?;
    Ok(())
}
