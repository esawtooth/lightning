use axum::{
    extract::{Path, State},
    response::Json,
    http::StatusCode,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use crate::state::AppState;
use context_hub_core::filesystem::{ContextHubFS, SyncStrategy, FilesystemMount};

#[derive(Debug, Serialize, Deserialize)]
pub struct MountRequest {
    /// Local path where Context Hub will be mounted
    pub mount_point: PathBuf,
    /// Sync strategy for the mount
    pub sync_strategy: SyncStrategy,
    /// Optional: specific folder ID to mount (defaults to root)
    pub folder_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct MountInfo {
    pub mount_point: PathBuf,
    pub status: MountStatus,
    pub sync_strategy: SyncStrategy,
    pub folder_id: Option<String>,
    pub stats: MountStats,
}

#[derive(Debug, Serialize)]
pub struct MountStats {
    pub total_documents: u64,
    pub synced_documents: u64,
    pub pending_changes: u64,
    pub last_sync: Option<i64>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MountStatus {
    Mounted,
    Unmounted,
    Syncing,
    Error(String),
}

/// Mount Context Hub as a filesystem
pub async fn mount_filesystem(
    State(state): State<AppState>,
    Json(request): Json<MountRequest>,
) -> Result<Json<MountInfo>, StatusCode> {
    // Validate mount point
    if !request.mount_point.exists() {
        std::fs::create_dir_all(&request.mount_point)
            .map_err(|_| StatusCode::BAD_REQUEST)?;
    }

    // Create filesystem instance
    let fs = ContextHubFS::new(
        state.storage.clone(),
        request.mount_point.clone(),
        request.sync_strategy.clone(),
    );

    // Platform-specific mounting
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    {
        use context_hub_core::filesystem::fuse::ContextHubFuse;
        let fuse_fs = ContextHubFuse::new(state.storage.clone());
        
        // Mount in background
        tokio::spawn(async move {
            fuser::mount2(fuse_fs, &request.mount_point, &[])
                .expect("Failed to mount filesystem");
        });
    }

    #[cfg(target_os = "windows")]
    {
        use context_hub_core::filesystem::winfsp::ContextHubWinFsp;
        let win_fs = ContextHubWinFsp::new(state.storage.clone());
        win_fs.mount(&request.mount_point).await
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    }

    // Register mount in state
    state.mounts.write().await.insert(
        request.mount_point.clone(),
        fs,
    );

    // Start file watcher for bidirectional sync
    if matches!(request.sync_strategy, SyncStrategy::Bidirectional) {
        start_file_watcher(state.clone(), request.mount_point.clone()).await;
    }

    Ok(Json(MountInfo {
        mount_point: request.mount_point,
        status: MountStatus::Mounted,
        sync_strategy: request.sync_strategy,
        folder_id: request.folder_id,
        stats: MountStats {
            total_documents: 0,
            synced_documents: 0,
            pending_changes: 0,
            last_sync: None,
        },
    }))
}

/// Unmount a filesystem
pub async fn unmount_filesystem(
    State(state): State<AppState>,
    Path(mount_point): Path<String>,
) -> Result<StatusCode, StatusCode> {
    let mount_path = PathBuf::from(mount_point);
    
    // Remove from active mounts
    if let Some(fs) = state.mounts.write().await.remove(&mount_path) {
        fs.unmount().await
            .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(StatusCode::NOT_FOUND)
    }
}

/// List all active mounts
pub async fn list_mounts(
    State(state): State<AppState>,
) -> Json<Vec<MountInfo>> {
    let mounts = state.mounts.read().await;
    let mount_infos = mounts.iter().map(|(path, fs)| {
        MountInfo {
            mount_point: path.clone(),
            status: if fs.is_mounted().await {
                MountStatus::Mounted
            } else {
                MountStatus::Unmounted
            },
            sync_strategy: fs.sync_strategy.clone(),
            folder_id: fs.folder_id.clone(),
            stats: get_mount_stats(&fs).await,
        }
    }).collect();
    
    Json(mount_infos)
}

/// Watch filesystem for changes and sync to Context Hub
async fn start_file_watcher(state: AppState, mount_point: PathBuf) {
    use notify::{Watcher, RecursiveMode, watcher};
    use std::sync::mpsc::channel;
    use std::time::Duration;

    let (tx, rx) = channel();
    let mut watcher = watcher(tx, Duration::from_secs(2)).unwrap();
    
    watcher.watch(&mount_point, RecursiveMode::Recursive).unwrap();

    tokio::spawn(async move {
        loop {
            match rx.recv() {
                Ok(event) => {
                    handle_filesystem_event(state.clone(), event).await;
                }
                Err(e) => {
                    eprintln!("Watch error: {:?}", e);
                    break;
                }
            }
        }
    });
}