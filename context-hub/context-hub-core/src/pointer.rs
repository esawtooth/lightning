use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use anyhow::{anyhow, Result};
use git2::{ObjectType, Repository};
use serde::Deserialize;

use crate::storage::crdt::Pointer;

/// Trait for resolving and storing pointer targets.
pub trait PointerResolver: Send + Sync {
    /// Store data for the given pointer.
    fn store(&self, pointer: &Pointer, data: &[u8]) -> Result<()>;
    /// Fetch the data referenced by the given pointer.
    fn fetch(&self, pointer: &Pointer) -> Result<Vec<u8>>;
}

/// Simple in-memory resolver used for testing.
pub struct InMemoryResolver {
    data: Mutex<HashMap<String, Vec<u8>>>,
}

impl InMemoryResolver {
    pub fn new() -> Self {
        Self {
            data: Mutex::new(HashMap::new()),
        }
    }
}

impl PointerResolver for InMemoryResolver {
    fn store(&self, pointer: &Pointer, data: &[u8]) -> Result<()> {
        let mut map = self.data.lock().unwrap();
        map.insert(pointer.target.clone(), data.to_vec());
        Ok(())
    }

    fn fetch(&self, pointer: &Pointer) -> Result<Vec<u8>> {
        let map = self.data.lock().unwrap();
        map.get(&pointer.target)
            .cloned()
            .ok_or_else(|| anyhow!("pointer not found"))
    }
}

/// Simple filesystem-backed resolver storing blobs under a directory.
pub struct BlobPointerResolver {
    dir: std::path::PathBuf,
}

impl BlobPointerResolver {
    /// Create a new resolver writing files to the given directory.
    pub fn new(dir: impl Into<std::path::PathBuf>) -> Result<Self> {
        let dir = dir.into();
        std::fs::create_dir_all(&dir)?;
        Ok(Self { dir })
    }
}

impl PointerResolver for BlobPointerResolver {
    fn store(&self, pointer: &Pointer, data: &[u8]) -> Result<()> {
        let path = self.dir.join(&pointer.target);
        std::fs::write(path, data)?;
        Ok(())
    }

    fn fetch(&self, pointer: &Pointer) -> Result<Vec<u8>> {
        let path = self.dir.join(&pointer.target);
        Ok(std::fs::read(path)?)
    }
}

/// Target information for a Git pointer.
#[derive(Deserialize)]
struct GitTarget {
    repo: String,
    path: String,
    #[serde(default)]
    rev: Option<String>,
}

/// Resolver fetching files from a Git repository.
pub struct GitPointerResolver {
    cache: std::path::PathBuf,
}

impl GitPointerResolver {
    /// Create a resolver caching clones under the given directory.
    pub fn new(dir: impl Into<std::path::PathBuf>) -> Result<Self> {
        let dir = dir.into();
        std::fs::create_dir_all(&dir)?;
        Ok(Self { cache: dir })
    }

    fn repo_path(&self, url: &str) -> std::path::PathBuf {
        let sanitized: String = url
            .chars()
            .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
            .collect();
        self.cache.join(sanitized)
    }
}

impl PointerResolver for GitPointerResolver {
    fn store(&self, _pointer: &Pointer, _data: &[u8]) -> Result<()> {
        Err(anyhow!("git pointers are read-only"))
    }

    fn fetch(&self, pointer: &Pointer) -> Result<Vec<u8>> {
        let target: GitTarget = serde_json::from_str(&pointer.target)?;
        let repo_dir = self.repo_path(&target.repo);
        let repo = if repo_dir.exists() {
            Repository::open(&repo_dir)?
        } else {
            Repository::clone(&target.repo, &repo_dir)?
        };

        let rev = target.rev.as_deref().unwrap_or("HEAD");
        let obj = repo.revparse_single(rev)?;
        let commit = obj.peel_to_commit()?;
        let tree = commit.tree()?;
        let entry = tree.get_path(std::path::Path::new(&target.path))?;
        if entry.kind() != Some(ObjectType::Blob) {
            return Err(anyhow!("target is not a file"));
        }
        let blob = repo.find_blob(entry.id())?;
        Ok(blob.content().to_vec())
    }
}

/// Registry mapping pointer types to concrete resolvers.
#[derive(Default)]
pub struct ResolverRegistry {
    resolvers: HashMap<String, Arc<dyn PointerResolver>>,
}

impl ResolverRegistry {
    pub fn new() -> Self {
        Self {
            resolvers: HashMap::new(),
        }
    }

    pub fn register(&mut self, kind: impl Into<String>, resolver: Arc<dyn PointerResolver>) {
        self.resolvers.insert(kind.into(), resolver);
    }

    pub fn get(&self, kind: &str) -> Option<&Arc<dyn PointerResolver>> {
        self.resolvers.get(kind)
    }
}
