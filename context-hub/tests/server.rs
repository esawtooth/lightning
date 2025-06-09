use context_hub::{api, storage};
use axum::{routing::get, Router};
use std::future::IntoFuture;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use std::time::Duration;

#[tokio::test]
async fn server_health_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = storage::crdt::DocumentStore::new(tempdir.path()).unwrap();
    let router = api::router(Arc::new(Mutex::new(store)));
    let app = Router::new().merge(router).route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(axum::serve(listener, app.into_make_service()).into_future());

    tokio::time::sleep(Duration::from_millis(100)).await;
    let resp = reqwest::get(format!("http://{}/health", addr))
        .await
        .unwrap();
    assert!(resp.status().is_success());
    let text = resp.text().await.unwrap();
    assert_eq!(text, "OK");

    server.abort();
}
