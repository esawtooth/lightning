use axum::{routing::get, Router};
use context_hub::{api, auth::Hs256Verifier, indexer, search, storage};
use futures_util::StreamExt;
use bytes::Bytes;
use std::future::IntoFuture;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::Mutex;

async fn next_event<S>(stream: &mut S) -> String
where
    S: futures_util::Stream<Item = Result<Bytes, reqwest::Error>> + Unpin,
{
    let mut buf = Vec::new();
    while let Some(chunk) = stream.next().await {
        let c = chunk.unwrap();
        buf.extend_from_slice(&c);
        if buf.ends_with(b"\n\n") {
            let text = String::from_utf8_lossy(&buf);
            for line in text.lines() {
                if let Some(rest) = line.strip_prefix("data: ") {
                    return rest.to_string();
                }
            }
            buf.clear();
        }
    }
    String::new()
}

#[tokio::test]
async fn realtime_updates_stream() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(storage::crdt::DocumentStore::new(tempdir.path()).unwrap()));
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let verifier = Arc::new(Hs256Verifier::new("secret".into()));
    let router = api::router(
        store.clone(),
        tempdir.path().into(),
        indexer,
        events.clone(),
        verifier,
    );
    let app = Router::new().merge(router).route("/health", get(|| async { "OK" }));

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let server = tokio::spawn(axum::serve(listener, app.into_make_service()).into_future());

    tokio::time::sleep(Duration::from_millis(100)).await;

    let client = reqwest::Client::new();
    let mut resp = client
        .get(format!("http://{}/ws", addr))
        .header("X-User-Id", "user1")
        .send()
        .await
        .unwrap();
    let mut stream = resp.bytes_stream();

    // create document
    let req = client
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
    assert!(req.status().is_success());
    let body: serde_json::Value = req.json().await.unwrap();
    let doc_id = body["id"].as_str().unwrap().to_string();

    let evt = next_event(&mut stream).await;
    assert!(evt.contains("\"Created\""));

    // update document
    let _ = client
        .put(format!("http://{}/docs/{}", addr, doc_id))
        .header("X-User-Id", "user1")
        .json(&serde_json::json!({
            "name": "note.txt",
            "content": "bye",
            "parent_folder_id": serde_json::Value::Null,
            "doc_type": "Text"
        }))
        .send()
        .await
        .unwrap();

    let evt2 = next_event(&mut stream).await;
    assert!(evt2.contains("\"Updated\""));

    server.abort();
}
