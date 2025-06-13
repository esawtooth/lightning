use criterion::{criterion_group, criterion_main, Criterion};
use context_hub::{search::SearchIndex, storage::crdt::{DocumentStore, DocumentType}};
use tempfile::TempDir;

fn bench_index_and_search(c: &mut Criterion) {
    let tempdir = TempDir::new().unwrap();
    let data_dir = tempdir.path().join("data");
    let index_dir = tempdir.path().join("index");
    std::fs::create_dir_all(&index_dir).unwrap();

    let mut store = DocumentStore::new(&data_dir).unwrap();
    for i in 0..100 {
        let name = format!("doc{}.txt", i);
        store
            .create(name, "hello", "user1".to_string(), None, DocumentType::Text)
            .unwrap();
    }
    let index = SearchIndex::new(&index_dir).unwrap();

    c.bench_function("index_all", |b| {
        b.iter(|| index.index_all(&store).unwrap())
    });

    index.index_all(&store).unwrap();
    c.bench_function("search_hello", |b| {
        b.iter(|| index.search("hello", 10).unwrap())
    });
}

criterion_group!(benches, bench_index_and_search);
criterion_main!(benches);
