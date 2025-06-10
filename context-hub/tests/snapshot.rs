use context_hub::snapshot::SnapshotManager;
use context_hub::storage::crdt::{DocumentStore, DocumentType};
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::Duration;
use tokio::task::LocalSet;

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
    mgr.snapshot(&store).unwrap();

    assert!(repo_dir.join(".git").exists());
    let repo = git2::Repository::open(repo_dir).unwrap();
    assert!(repo.revparse_single("HEAD").is_ok());
}

#[tokio::test]
async fn snapshot_task_runs() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    let data_dir = tempdir.path().join("data");
    let store = Arc::new(Mutex::new(DocumentStore::new(&data_dir).unwrap()));
    {
        let mut s = store.lock().await;
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
    ));
    local.run_until(tokio::time::sleep(Duration::from_millis(150))).await;

    assert!(repo_dir.join(".git").exists());
    let repo = git2::Repository::open(repo_dir).unwrap();
    assert!(repo.revparse_single("HEAD").is_ok());
}
