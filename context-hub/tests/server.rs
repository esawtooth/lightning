use axum::{routing::get, Router};
use context_hub::pointer::BlobPointerResolver;
use context_hub::{api, indexer, search, storage};
use std::future::IntoFuture;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tower::util::ServiceExt;

#[tokio::test]
async fn server_health_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let router = api::router(store.clone(), tempdir.path().into(), indexer, events);
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
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let app = Router::new().merge(api::router(
        store.clone(),
        tempdir.path().into(),
        indexer,
        events,
    ));

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

#[tokio::test]
async fn search_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let app = Router::new().merge(api::router(
        store.clone(),
        tempdir.path().into(),
        indexer.clone(),
        events,
    ));

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "note.txt",
                "content": "hello world",
                "parent_folder_id": null,
                "doc_type": "Text"
            })
            .to_string(),
        ))
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    tokio::time::sleep(Duration::from_millis(200)).await;

    let req = axum::http::Request::builder()
        .uri("/search?q=hello")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(v.as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn rename_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let app = Router::new().merge(api::router(
        store.clone(),
        tempdir.path().into(),
        indexer.clone(),
        events,
    ));

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "note.txt",
                "content": "hello",
                "parent_folder_id": null,
                "doc_type": "Text"
            })
            .to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let doc_id = v["id"].as_str().unwrap();

    let req = axum::http::Request::builder()
        .method("PUT")
        .uri(format!("/docs/{}/rename", doc_id))
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({"name": "renamed.txt"}).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::NO_CONTENT);

    let req = axum::http::Request::builder()
        .uri("/search?q=renamed")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert!(arr.iter().any(|v| v["id"].as_str().unwrap() == doc_id));
    assert_eq!(arr[0]["name"].as_str().unwrap(), "renamed.txt");
}

#[tokio::test]
async fn move_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let app = Router::new().merge(api::router(
        store.clone(),
        tempdir.path().into(),
        indexer.clone(),
        events,
    ));

    let root = {
        let mut s = store.lock().await;
        s.ensure_root("user1").unwrap()
    };

    // create source and destination folders
    let src_req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "src", "content": "", "parent_folder_id": root,
                "doc_type": "Folder"
            })
            .to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(src_req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let src_id = v["id"].as_str().unwrap();

    let dst_req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "dst", "content": "", "parent_folder_id": root,
                "doc_type": "Folder"
            })
            .to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(dst_req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let dst_id = v["id"].as_str().unwrap();

    // create a document inside src
    let doc_req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "note.txt", "content": "hello", "parent_folder_id": src_id,
                "doc_type": "Text"
            })
            .to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(doc_req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let doc_id = v["id"].as_str().unwrap();

    // move the document to dst
    let move_req = axum::http::Request::builder()
        .method("PUT")
        .uri(format!("/docs/{}/move", doc_id))
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({ "new_parent_folder_id": dst_id }).to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(move_req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::NO_CONTENT);

    // search should include folder name dst after move
    tokio::time::sleep(Duration::from_millis(200)).await;
    let search_req = axum::http::Request::builder()
        .uri("/search?q=dst")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(search_req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert!(arr.iter().any(|v| v["id"].as_str().unwrap() == doc_id));

    // src folder should only contain its index guide now
    let list_req = axum::http::Request::builder()
        .uri(format!("/folders/{}", src_id))
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(list_req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert_eq!(arr.len(), 1);

    // dst folder should contain index guide and moved doc
    let list_req = axum::http::Request::builder()
        .uri(format!("/folders/{}", dst_id))
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(list_req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert_eq!(arr.len(), 2);
}

#[tokio::test]
async fn blob_attach_and_fetch() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(
        storage::crdt::DocumentStore::new(tempdir.path()).unwrap(),
    ));
    {
        let mut s = store.lock().await;
        let resolver = Arc::new(
            context_hub::pointer::BlobPointerResolver::new(tempdir.path().join("blobs")).unwrap(),
        );
        s.register_resolver("blob", resolver);
    }
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let app = Router::new().merge(api::router(
        store.clone(),
        tempdir.path().into(),
        indexer.clone(),
        events,
    ));

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/docs")
        .header("X-User-Id", "user1")
        .header("content-type", "application/json")
        .body(axum::body::Body::from(
            serde_json::json!({
                "name": "note.txt",
                "content": "hello",
                "parent_folder_id": null,
                "doc_type": "Text"
            })
            .to_string(),
        ))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&body).unwrap();
    let doc_id = v["id"].as_str().unwrap();

    let req = axum::http::Request::builder()
        .method("POST")
        .uri(format!("/docs/{}/content?name=file.bin", doc_id))
        .header("X-User-Id", "user1")
        .body(axum::body::Body::from("payload"))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);

    let req = axum::http::Request::builder()
        .uri(format!("/docs/{}/content/1", doc_id))
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let data = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    assert_eq!(data, axum::body::Bytes::from_static(b"payload"));
}
