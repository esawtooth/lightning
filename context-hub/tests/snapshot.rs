use context_hub::{
    indexer, search,
    snapshot::SnapshotManager,
    storage::crdt::{DocumentStore, DocumentType},
};
use context_hub::auth::legacy::Hs256Verifier;
use chrono::TimeZone;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::task::LocalSet;
use tokio::time::Duration;
use tower::util::ServiceExt;

#[test]
fn init_repo_creates_git_dir() {
    let tempdir = tempfile::tempdir().unwrap();
    let path = tempdir.path();
    SnapshotManager::new(path).unwrap();
    assert!(path.join(".git").exists());
}

#[test]
fn snapshot_commits_files() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let mut store = DocumentStore::new(&data_dir).unwrap();
    store
        .create(
            "note.txt".to_string(),
            "hi",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();

    let mgr = SnapshotManager::new(&repo_dir).unwrap();
    let _commit = mgr.snapshot(&store).unwrap();

    assert!(repo_dir.join(".git").exists());
    let repo = git2::Repository::open(repo_dir).unwrap();
    assert!(repo.revparse_single("HEAD").is_ok());
}

#[tokio::test]
async fn snapshot_task_runs() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let store = Arc::new(RwLock::new(DocumentStore::new(&data_dir).unwrap()));
    {
        let mut s = store.write().await;
        s.create(
            "note.txt".to_string(),
            "hi",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    }
    let mgr = Arc::new(SnapshotManager::new(&repo_dir).unwrap());
    let local = LocalSet::new();
    local.spawn_local(context_hub::snapshot::snapshot_task(
        store.clone(),
        mgr.clone(),
        Duration::from_millis(100),
        None,
    ));
    local
        .run_until(tokio::time::sleep(Duration::from_millis(150)))
        .await;

    assert!(repo_dir.join(".git").exists());
    let repo = git2::Repository::open(repo_dir).unwrap();
    assert!(repo.revparse_single("HEAD").is_ok());
}

#[tokio::test]
#[ignore] // Requires full API implementation
async fn snapshot_endpoint_triggers_commit() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let store = Arc::new(RwLock::new(DocumentStore::new(&data_dir).unwrap()));
    {
        let mut s = store.write().await;
        s.create(
            "note.txt".to_string(),
            "hi",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    }
    let index_dir = repo_dir.join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let verifier = Arc::new(Hs256Verifier::new("secret".into()));
    let app = context_hub::api::router(
        store.clone(),
        repo_dir.clone(),
        None,
        indexer,
        events,
        verifier,
    );

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/snapshot")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    assert!(repo_dir.join(".git").exists());
    let repo = git2::Repository::open(repo_dir).unwrap();
    assert!(repo.revparse_single("HEAD").is_ok());
}

#[test]
fn restore_reverts_state() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let mut store = DocumentStore::new(&data_dir).unwrap();
    let doc1 = store
        .create(
            "one.txt".to_string(),
            "one",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    let doc2 = store
        .create(
            "two.txt".to_string(),
            "two",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    let mgr = SnapshotManager::new(&repo_dir).unwrap();
    let commit = mgr.snapshot(&store).unwrap();

    store.update(doc1, "changed").unwrap();
    store.delete(doc2).unwrap();

    mgr.restore(&mut store, &commit.to_string()).unwrap();

    assert_eq!(store.get(doc1).unwrap().text(), "one");
    assert!(store.get(doc2).is_some());
}

#[test]
fn restore_by_timestamp() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let mut store = DocumentStore::new(&data_dir).unwrap();
    let doc = store
        .create(
            "ts.txt".to_string(),
            "v1",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    let mgr = SnapshotManager::new(&repo_dir).unwrap();
    let commit = mgr.snapshot(&store).unwrap();

    std::thread::sleep(std::time::Duration::from_secs(1));

    store.update(doc, "v2").unwrap();
    let _c2 = mgr.snapshot(&store).unwrap();

    let repo = git2::Repository::open(&repo_dir).unwrap();
    let commit_obj = repo.find_commit(commit).unwrap();
    let ts = chrono::Utc
        .timestamp_opt(commit_obj.time().seconds(), 0)
        .single()
        .unwrap()
        .to_rfc3339();

    store.update(doc, "v3").unwrap();

    mgr.restore(&mut store, &ts).unwrap();
    assert_eq!(store.get(doc).unwrap().text(), "v1");
}

#[tokio::test]
#[ignore] // Requires full API implementation
async fn snapshot_listing_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let store = Arc::new(RwLock::new(DocumentStore::new(&data_dir).unwrap()));
    let index_dir = repo_dir.join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let verifier = Arc::new(Hs256Verifier::new("secret".into()));
    let app = context_hub::api::router(
        store.clone(),
        repo_dir.clone(),
        None,
        indexer,
        events,
        verifier,
    );

    {
        let mut s = store.write().await;
        s.create(
            "a.txt".to_string(),
            "hi",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();
    }

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/snapshot")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    let req = axum::http::Request::builder()
        .uri("/snapshots")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    assert!(!arr.is_empty());
}

#[tokio::test]
#[ignore] // Requires full API implementation
async fn snapshot_fetch_doc_endpoint() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let store = Arc::new(RwLock::new(DocumentStore::new(&data_dir).unwrap()));
    let index_dir = repo_dir.join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let search = Arc::new(search::SearchIndex::new(&index_dir).unwrap());
    let indexer = Arc::new(indexer::LiveIndex::new(search.clone(), store.clone()));
    let events = context_hub::events::EventBus::new();
    let verifier = Arc::new(Hs256Verifier::new("secret".into()));
    let app = context_hub::api::router(
        store.clone(),
        repo_dir.clone(),
        None,
        indexer,
        events,
        verifier,
    );

    let doc_id = {
        let mut s = store.write().await;
        s.create(
            "a.txt".to_string(),
            "v1",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap()
    };

    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/snapshot")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    {
        let mut s = store.write().await;
        s.update(doc_id, "v2").unwrap();
    }
    let req = axum::http::Request::builder()
        .method("POST")
        .uri("/snapshot")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let _ = app.clone().oneshot(req).await.unwrap();

    let req = axum::http::Request::builder()
        .uri("/snapshots")
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let arr: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
    let rev = arr.first().unwrap()["id"].as_str().unwrap();

    let req = axum::http::Request::builder()
        .uri(format!("/snapshots/{}/docs/{}", rev, doc_id))
        .header("X-User-Id", "user1")
        .body(axum::body::Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), axum::http::StatusCode::OK);
    let body = axum::body::to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let val: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(val["content"].as_str().unwrap(), "v2");
}
