use context_hub::{
    pointer::{InMemoryResolver, PointerResolver},
    storage::crdt::{DocumentStore, DocumentType, Pointer},
};
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
