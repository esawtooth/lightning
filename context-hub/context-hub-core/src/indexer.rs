use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{RwLock, Mutex as AsyncMutex};
use tokio::time::{sleep, Duration};
use uuid::Uuid;

use anyhow::Result;

use crate::search::SearchIndex;
use crate::storage::crdt::DocumentStore;

pub struct LiveIndex {
    index: Arc<SearchIndex>,
    store: Arc<RwLock<DocumentStore>>,
    pending: AsyncMutex<HashMap<Uuid, tokio::task::JoinHandle<()>>>,
}

impl LiveIndex {
    pub fn new(index: Arc<SearchIndex>, store: Arc<RwLock<DocumentStore>>) -> Self {
        Self {
            index,
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

    async fn reindex(index: Arc<SearchIndex>, store: Arc<RwLock<DocumentStore>>, id: Uuid) {
        sleep(Duration::from_millis(100)).await;
        let store_guard = store.read().await;
        if let Some(doc) = store_guard.get(id) {
            let folders = Self::gather_folders(&store_guard, doc.parent_folder_id());
            let _ = index.index_document(id, doc.name(), &doc.text(), &folders);
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
        let store = self.store.clone();
        let handle = tokio::spawn(Self::reindex(index, store, id));
        pending.insert(id, handle);
    }
}

impl LiveIndex {
    pub async fn schedule_recursive_delete(&self, ids: Vec<Uuid>) {
        for id in ids {
            self.schedule_update(id).await;
        }
    }

    pub async fn schedule_recursive_update(&self, ids: Vec<Uuid>) {
        for id in ids {
            self.schedule_update(id).await;
        }
    }

    pub fn search(&self, query: &str, limit: usize) -> Result<Vec<Uuid>> {
        self.index.search(query, limit)
    }
}
