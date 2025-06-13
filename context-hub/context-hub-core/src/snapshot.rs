use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};

use crate::storage::crdt::DocumentStore;
use anyhow::{anyhow, Result};
use chrono::{TimeZone, Utc};
use git2::{IndexAddOption, ObjectType, Oid, Repository, Signature};
use crate::storage::crdt::Document;
use uuid::Uuid;

pub struct SnapshotManager {
    repo: Repository,
}

#[derive(Debug, Clone)]
pub struct SnapshotInfo {
    pub id: Oid,
    pub time: chrono::DateTime<Utc>,
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
        let ts = Utc::now();
        let msg = format!("Snapshot {}", ts.to_rfc3339());
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
        let tag_name = format!("snapshot-{}", ts.timestamp());
        let obj = self.repo.find_object(commit_id, None)?;
        let _ = self.repo.tag_lightweight(&tag_name, &obj, false);
        Ok(commit_id)
    }

    pub fn prune_old_tags(&self, keep: usize) -> Result<()> {
        let names = self.repo.tag_names(Some("snapshot-*"))?;
        let mut entries = Vec::new();
        for name in names.iter().flatten() {
            if let Ok(obj) = self.repo.revparse_single(name) {
                if let Ok(commit) = obj.peel_to_commit() {
                    let ts = Utc
                        .timestamp_opt(commit.time().seconds(), 0)
                        .single()
                        .unwrap();
                    entries.push((name.to_string(), ts));
                }
            }
        }
        entries.sort_by_key(|e| e.1);
        while entries.len() > keep {
            if let Some((name, _)) = entries.first() {
                let _ = self.repo.tag_delete(name);
                entries.remove(0);
            }
        }
        Ok(())
    }

    pub fn repo(&self) -> &Repository {
        &self.repo
    }

    fn resolve_rev(&self, rev: &str) -> Result<Oid> {
        if let Ok(ts) = chrono::DateTime::parse_from_rfc3339(rev) {
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
            found.ok_or_else(|| anyhow!("no commit before timestamp"))
        } else {
            Ok(self.repo.revparse_single(rev)?.peel_to_commit()?.id())
        }
    }

    pub fn history(&self, limit: usize) -> Result<Vec<SnapshotInfo>> {
        let mut walk = self.repo.revwalk()?;
        walk.push_head()?;
        let mut out = Vec::new();
        for (i, id) in walk.enumerate() {
            if i >= limit {
                break;
            }
            let id = id?;
            let commit = self.repo.find_commit(id)?;
            let ts = Utc
                .timestamp_opt(commit.time().seconds(), 0)
                .single()
                .unwrap();
            out.push(SnapshotInfo { id, time: ts });
        }
        Ok(out)
    }

    pub fn load_document_at(&self, doc: Uuid, rev: &str) -> Result<Option<Document>> {
        let oid = self.resolve_rev(rev)?;
        let commit = self.repo.find_commit(oid)?;
        let tree = commit.tree()?;
        let name = format!("{}.bin", doc);
        if let Some(entry) = tree.get_name(&name) {
            if entry.kind() == Some(ObjectType::Blob) {
                let blob = self.repo.find_blob(entry.id())?;
                let doc = Document::from_bytes(doc, blob.content())?;
                return Ok(Some(doc));
            }
        }
        Ok(None)
    }

    /// Restore the document store state from the specified revision. The
    /// `rev` can be any git revspec (commit hash or tag) or an RFC3339
    /// timestamp, in which case the latest commit at or before that time is
    /// used.
    pub fn restore(&self, store: &mut DocumentStore, rev: &str) -> Result<()> {
        let oid = self.resolve_rev(rev)?;

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
    retention: Option<usize>,
) {
    let mut ticker = interval(period);
    loop {
        ticker.tick().await;
        let mut store = store.write().await;
        if store.is_dirty() {
            if manager.snapshot(&store).is_ok() {
                if let Some(max) = retention {
                    let _ = manager.prune_old_tags(max);
                }
            }
            store.clear_dirty();
            let _ = store.compact_history();
        }
    }
}
