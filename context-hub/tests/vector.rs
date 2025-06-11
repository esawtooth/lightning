use context_hub::vector::VectorIndex;
use uuid::Uuid;

#[test]
fn vector_index_search() {
    let mut index = VectorIndex::new().unwrap();
    let id = Uuid::new_v4();
    index.index_document(id, "hello world").unwrap();
    let res = index.search("hello", 1).unwrap();
    assert_eq!(res.len(), 1);
    assert_eq!(res[0], id);
}
