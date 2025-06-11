use axum::{routing::get, Router};
use context_hub::{api, search, storage, indexer, vector};
use std::future::IntoFuture;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tower::util::ServiceExt;

#[tokio::test]
async fn server_health_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new(tempdir.path()).unwrap()));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let vectors = Arc::new(Mutex::new(context_hub::vector::VectorIndex::new().unwrap()));
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), vectors.clone(), store.clone()));
    let router = api::router(store.clone(), tempdir.path().into(), indexer);
    let app = Router::new()
        .merge(router)
        .route("/health", get(|| async { "OK" }));

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

#[tokio::test]
async fn root_created_on_use() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new(tempdir.path()).unwrap()));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let vectors = Arc::new(Mutex::new(context_hub::vector::VectorIndex::new().unwrap()));
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), vectors.clone(), store.clone()));
    let app = Router::new().merge(api::router(store.clone(), tempdir.path().into(), indexer));

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "newuser")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "a.txt",
                "content": "hi",
                "parent_folder_id": null,
                "doc_type": "Text"
            })
            .to_string(),
        ))
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    let mut store_guard = store.lock().await;
    assert!(store_guard.ensure_root("newuser").is_ok());
}
