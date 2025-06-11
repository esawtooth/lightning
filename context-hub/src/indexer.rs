use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{Mutex, Mutex as AsyncMutex};
use tokio::time::{sleep, Duration};
use uuid::Uuid;

use crate::search::SearchIndex;
use crate::vector::VectorIndex;
use crate::storage::crdt::DocumentStore;

pub struct LiveIndex {
    index: Arc<SearchIndex>,
    vectors: Arc<Mutex<VectorIndex>>,
    store: Arc<Mutex<DocumentStore>>,
    pending: AsyncMutex<HashMap<Uuid, tokio::task::JoinHandle<()>>>,
}

impl LiveIndex {
    pub fn new(
        index: Arc<SearchIndex>,
        vectors: Arc<Mutex<VectorIndex>>, 
        store: Arc<Mutex<DocumentStore>>,
    ) -> Self {
        Self {
            index,
            vectors,
            store,
            pending: AsyncMutex::new(HashMap::new()),
        }
    }

    fn gather_folders(store: &DocumentStore, mut current: Option<Uuid>) -> Vec<String> {
        let mut folders = Vec::new();
        while let Some(pid) = current {
            if let Some(doc) = store.get(pid) {
                folders.push(doc.name().to_string());
                current = doc.parent_folder_id();
            } else {
                break;
            }
        }
        folders
    }

    async fn reindex(
        index: Arc<SearchIndex>,
        vectors: Arc<Mutex<VectorIndex>>,
        store: Arc<Mutex<DocumentStore>>,
        id: Uuid,
    ) {
        sleep(Duration::from_millis(100)).await;
        let store_guard = store.lock().await;
        if let Some(doc) = store_guard.get(id) {
            let folders = Self::gather_folders(&store_guard, doc.parent_folder_id());
            let text = doc.text();
            let _ = index.index_document(id, doc.name(), &text, &folders);
            drop(store_guard);
            let mut v = vectors.lock().await;
            let _ = v.index_document(id, &text);
        } else {
            let _ = index.remove_document(id);
        }
    }

    pub async fn schedule_update(&self, id: Uuid) {
        let mut pending = self.pending.lock().await;
        if let Some(handle) = pending.remove(&id) {
            handle.abort();
        }
        let index = self.index.clone();
        let vectors = self.vectors.clone();
        let store = self.store.clone();
        let handle = tokio::spawn(Self::reindex(index, vectors, store, id));
        pending.insert(id, handle);
    }
}

impl LiveIndex {
    pub async fn schedule_recursive_delete(&self, ids: Vec<Uuid>) {
        for id in ids {
            self.schedule_update(id).await;
        }
    }
}
