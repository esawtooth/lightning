use std::path::Path;

use anyhow::Result;
use git2::Repository;

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

    /// Placeholder for future snapshot logic
    pub fn repo(&self) -> &Repository {
        &self.repo
    }
}
