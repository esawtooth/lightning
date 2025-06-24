use std::path::{Path, PathBuf};
use async_trait::async_trait;
use crate::storage::crdt::{Document, DocumentType};
use crate::pointer::PointerResolver;

/// Trait for filesystem operations that abstracts across platforms
#[async_trait]
pub trait FilesystemMount {
    async fn mount(&self, mount_point: &Path) -> Result<(), FilesystemError>;
    async fn unmount(&self) -> Result<(), FilesystemError>;
    async fn is_mounted(&self) -> bool;
}

/// FUSE implementation for Linux/macOS
#[cfg(any(target_os = "linux", target_os = "macos"))]
pub mod fuse;

/// WinFsp implementation for Windows
#[cfg(target_os = "windows")]
pub mod winfsp;

/// Virtual filesystem that bridges Context Hub documents to filesystem operations
pub struct ContextHubFS {
    storage: Arc<dyn Storage>,
    mount_point: PathBuf,
    sync_strategy: SyncStrategy,
}

#[derive(Debug, Clone)]
pub enum SyncStrategy {
    /// One-way sync from Context Hub to filesystem (read-only mount)
    ReadOnly,
    /// Two-way sync with CRDT conflict resolution
    Bidirectional,
    /// Offline-first with periodic sync
    OfflineFirst { sync_interval: Duration },
}

#[derive(Debug, thiserror::Error)]
pub enum FilesystemError {
    #[error("Mount failed: {0}")]
    MountFailed(String),
    #[error("Permission denied: {0}")]
    PermissionDenied(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}