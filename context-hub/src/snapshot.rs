use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::{interval, Duration};

use crate::storage::crdt::DocumentStore;
use anyhow::{anyhow, Result};
use chrono::Utc;
use git2::{IndexAddOption, Repository, Signature};

pub struct SnapshotManager {
    repo: Repository,
}

impl SnapshotManager {
    pub fn new(dir: impl AsRef<Path>) -> Result<Self> {
        let dir = dir.as_ref();
        let repo = if dir.join(".git").exists() {
            Repository::open(dir)?
        } else {
            std::fs::create_dir_all(dir)?;
            Repository::init(dir)?
        };
        Ok(Self { repo })
    }

    /// Commit the current document store state to the snapshot repository.
    pub fn snapshot(&self, store: &DocumentStore) -> Result<()> {
        let workdir = self
            .repo
            .workdir()
            .ok_or_else(|| anyhow!("snapshot repository has no working directory"))?;

        // copy all document files into the repo workdir
        for entry in std::fs::read_dir(store.data_dir())? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                let dest = PathBuf::from(workdir).join(entry.file_name());
                std::fs::copy(entry.path(), dest)?;
            }
        }

        // stage all changes
        let mut index = self.repo.index()?;
        index.add_all(["*"].iter(), IndexAddOption::DEFAULT, None)?;
        index.write()?;
        let tree_id = index.write_tree()?;
        let tree = self.repo.find_tree(tree_id)?;

        let sig = Signature::now("context-hub", "context@hub")?;
        let msg = format!("Snapshot {}", Utc::now().to_rfc3339());
        let commit_id = match self.repo.head() {
            Ok(head) => {
                let parent = head.peel_to_commit()?;
                self.repo
                    .commit(Some("HEAD"), &sig, &sig, &msg, &tree, &[&parent])?
            }
            Err(_) => self
                .repo
                .commit(Some("HEAD"), &sig, &sig, &msg, &tree, &[])?,
        };
        let _ = commit_id; // suppress unused warning
        Ok(())
    }

    pub fn repo(&self) -> &Repository {
        &self.repo
    }
}

/// Spawn a background task that periodically snapshots the document store.
pub async fn snapshot_task(
    store: Arc<Mutex<DocumentStore>>,
    manager: Arc<SnapshotManager>,
    period: Duration,
) {
    let mut ticker = interval(period);
    loop {
        ticker.tick().await;
        let mut store = store.lock().await;
        if store.is_dirty() {
            let _ = manager.snapshot(&store);
            store.clear_dirty();
        }
    }
}
