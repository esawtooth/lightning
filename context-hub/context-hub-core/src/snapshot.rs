use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

use crate::storage::crdt::DocumentStore;
use anyhow::{anyhow, Result};
use chrono::{TimeZone, Utc};
use git2::{IndexAddOption, ObjectType, Oid, Repository, Signature};

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
    pub fn snapshot(&self, store: &DocumentStore) -> Result<Oid> {
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
        Ok(commit_id)
    }

    pub fn repo(&self) -> &Repository {
        &self.repo
    }

    /// Restore the document store state from the specified revision. The
    /// `rev` can be any git revspec (commit hash or tag) or an RFC3339
    /// timestamp, in which case the latest commit at or before that time is
    /// used.
    pub fn restore(&self, store: &mut DocumentStore, rev: &str) -> Result<()> {
        let oid = if let Ok(ts) = chrono::DateTime::parse_from_rfc3339(rev) {
            let mut walk = self.repo.revwalk()?;
            walk.push_head()?;
            let ts = ts.with_timezone(&Utc);
            let mut found = None;
            for id in walk {
                let id = id?;
                let commit = self.repo.find_commit(id)?;
                let commit_time = Utc
                    .timestamp_opt(commit.time().seconds(), 0)
                    .single()
                    .unwrap();
                if commit_time <= ts {
                    found = Some(id);
                    break;
                }
            }
            found.ok_or_else(|| anyhow!("no commit before timestamp"))?
        } else {
            self.repo.revparse_single(rev)?.peel_to_commit()?.id()
        };

        let commit = self.repo.find_commit(oid)?;
        let tree = commit.tree()?;

        // clear current data directory
        for entry in std::fs::read_dir(store.data_dir())? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                std::fs::remove_file(entry.path())?;
            }
        }

        // materialize files from the tree
        for entry in tree.iter() {
            if entry.kind() == Some(ObjectType::Blob) {
                let blob = self.repo.find_blob(entry.id())?;
                let name = entry.name().ok_or_else(|| anyhow!("invalid path"))?;
                std::fs::write(store.data_dir().join(name), blob.content())?;
            }
        }

        store.reload()?;
        store.clear_dirty();
        Ok(())
    }
}

/// Spawn a background task that periodically snapshots the document store.
pub async fn snapshot_task(
    store: Arc<RwLock<DocumentStore>>,
    manager: Arc<SnapshotManager>,
    period: Duration,
) {
    let mut ticker = interval(period);
    loop {
        ticker.tick().await;
        let mut store = store.write().await;
        if store.is_dirty() {
            let _ = manager.snapshot(&store);
            store.clear_dirty();
            let _ = store.compact_history();
        }
    }
}
