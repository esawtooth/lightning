use context_hub::snapshot::SnapshotManager;

#[test]
fn init_repo_creates_git_dir() {
    let tempdir = tempfile::tempdir().unwrap();
    let path = tempdir.path();
    SnapshotManager::new(path).unwrap();
    assert!(path.join(".git").exists());
}
