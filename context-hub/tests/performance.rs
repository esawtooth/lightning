use context_hub::{search::SearchIndex, snapshot::SnapshotManager, storage::crdt::{DocumentStore, DocumentType}};

#[test]
fn index_and_snapshot_large_store() {
    let tempdir = tempfile::tempdir().unwrap();
    let data_dir = tempdir.path().join("data");
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();
    let mut store = DocumentStore::new(&data_dir).unwrap();
    for i in 0..100 {
        let name = format!("doc{}.txt", i);
        let _ = store.create(name, "hello", "user1".to_string(), None, DocumentType::Text).unwrap();
    }
    let index = SearchIndex::new(&index_dir).unwrap();
    index.index_all(&store).unwrap();
    assert!(!index.search("hello", 10).unwrap().is_empty());

    let mgr = SnapshotManager::new(tempdir.path().join("repo")).unwrap();
    let _ = mgr.snapshot(&store).unwrap();
    assert!(mgr.repo().revparse_single("HEAD").is_ok());
}
