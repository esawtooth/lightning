use context_hub::snapshot::SnapshotManager;
use context_hub::storage::crdt::{DocumentStore, DocumentType};

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
