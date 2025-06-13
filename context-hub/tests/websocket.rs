use axum::{routing::get, Router};
use context_hub::{api, auth::Hs256Verifier, indexer, search, storage};
use futures_util::{SinkExt, StreamExt};
use std::future::IntoFuture;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::RwLock;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;

#[tokio::test]
async fn doc_websocket_broadcasts_updates() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(RwLock::new(storage::crdt::DocumentStore::new(tempdir.path()).unwrap()));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let verifier = Arc::new(Hs256Verifier::new("secret".into()));
    let router = api::router(
        store.clone(),
        tempdir.path().into(),
        None,
        indexer,
        events,
        verifier,
    );
    let app = Router::new().merge(router).route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(axum::serve(listener, app.into_make_service()).into_future());

    tokio::time::sleep(Duration::from_millis(100)).await;

    let client = reqwest::Client::new();
    let resp = client
        .post(format!("http://{}/docs", addr))
        .header("X-User-Id", "user1")
        .json(&serde_json::json!({
            "name": "note.txt",
            "content": "hi",
            "parent_folder_id": serde_json::Value::Null,
            "doc_type": "Text"
        }))
        .send()
        .await
        .unwrap();
    assert!(resp.status().is_success());
    let body: serde_json::Value = resp.json().await.unwrap();
    let doc_id = body["id"].as_str().unwrap();

    let url = format!("ws://{}/ws/docs/{}", addr, doc_id);
    let mut req1 = url.clone().into_client_request().unwrap();
    req1.headers_mut().insert("X-User-Id", "user1".parse().unwrap());
    let (mut ws1, _) = connect_async(req1).await.unwrap();

    let mut req2 = url.clone().into_client_request().unwrap();
    req2.headers_mut().insert("X-User-Id", "user1".parse().unwrap());
    let (mut ws2, _) = connect_async(req2).await.unwrap();

    let _ = ws1.next().await.unwrap().unwrap();
    let _ = ws2.next().await.unwrap().unwrap();

    ws1.send(Message::Text("bye".into())).await.unwrap();

    if let Some(Ok(Message::Binary(data))) = ws2.next().await {
        assert_eq!(data, b"bye".to_vec());
    } else {
        panic!("did not receive update");
    }

    server.abort();
}
