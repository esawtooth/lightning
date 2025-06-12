use context_hub::storage::crdt::{DocumentStore, DocumentType};
use std::sync::Arc;
use tokio::sync::Mutex;

#[tokio::test]
async fn concurrent_updates_do_not_panic() {
    let tempdir = tempfile::tempdir().unwrap();
    let store = Arc::new(Mutex::new(DocumentStore::new(tempdir.path()).unwrap()));
    let doc_id = {
        let mut s = store.lock().await;
        s.create(
            "note.txt".to_string(),
            "hi",
            "user1".to_string(),
            None,
            DocumentType::Text,
        )
        .unwrap()
    };

    let s1 = store.clone();
    let s2 = store.clone();
    let t1 = tokio::spawn(async move {
        let mut s = s1.lock().await;
        s.update(doc_id, "one").unwrap();
    });
    let t2 = tokio::spawn(async move {
        let mut s = s2.lock().await;
        s.update(doc_id, "two").unwrap();
    });

    let _ = tokio::join!(t1, t2);

    let text = {
        let s = store.lock().await;
        s.get(doc_id).unwrap().text()
    };
    assert!(text == "one" || text == "two");
}
