use context_hub::{
    pointer::{GitPointerResolver, InMemoryResolver, PointerResolver},
    storage::crdt::{DocumentStore, DocumentType, Pointer},
};
use git2::Repository;
use std::sync::Arc;

#[test]
fn resolve_pointer_with_memory_resolver() {
    let tempdir = tempfile::tempdir().unwrap();
    let mut store = DocumentStore::new(tempdir.path()).unwrap();
    let resolver = Arc::new(InMemoryResolver::new());
    store.register_resolver("blob", resolver.clone());

    let doc_id = store
        .create(
            "file.txt".to_string(),
            "hello",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();

    let ptr = Pointer {
        pointer_type: "blob".to_string(),
        target: "123".to_string(),
        name: Some("data.bin".to_string()),
        preview_text: None,
    };
    resolver.store(&ptr, b"payload").unwrap();

    store.insert_pointer(doc_id, 1, ptr).unwrap();

    let data = store.resolve_pointer(doc_id, 1).unwrap();
    assert_eq!(data, b"payload".to_vec());
}

#[test]
fn resolve_git_pointer() {
    let tempdir = tempfile::tempdir().unwrap();
    let repo_dir = tempdir.path().join("repo");
    std::fs::create_dir_all(&repo_dir).unwrap();
    let repo = Repository::init(&repo_dir).unwrap();
    std::fs::write(repo_dir.join("file.txt"), b"hello git").unwrap();
    {
        let mut index = repo.index().unwrap();
        index.add_path(std::path::Path::new("file.txt")).unwrap();
        index.write().unwrap();
        let tree_id = index.write_tree().unwrap();
        let tree = repo.find_tree(tree_id).unwrap();
        let sig = repo.signature().unwrap();
        repo.commit(Some("HEAD"), &sig, &sig, "init", &tree, &[])
            .unwrap();
    }

    let mut store = DocumentStore::new(tempdir.path().join("data")).unwrap();
    let resolver = Arc::new(GitPointerResolver::new(tempdir.path().join("cache")).unwrap());
    store.register_resolver("git", resolver);

    let doc_id = store
        .create(
            "code".to_string(),
            "",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap();

    let head = repo.head().unwrap().target().unwrap();
    let target = serde_json::json!({
        "repo": repo_dir.to_str().unwrap(),
        "path": "file.txt",
        "rev": head.to_string(),
    })
    .to_string();

    let ptr = Pointer {
        pointer_type: "git".to_string(),
        target,
        name: Some("file.txt".to_string()),
        preview_text: None,
    };

    store.insert_pointer(doc_id, 0, ptr).unwrap();

    let data = store.resolve_pointer(doc_id, 0).unwrap();
    assert_eq!(data, b"hello git".to_vec());

    let data2 = store.resolve_pointer_by_name(doc_id, "file.txt").unwrap();
    assert_eq!(data2, b"hello git".to_vec());
}
