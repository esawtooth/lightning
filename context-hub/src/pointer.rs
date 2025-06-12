use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use anyhow::{anyhow, Result};

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
