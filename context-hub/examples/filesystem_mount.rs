use context_hub_core::filesystem::{SyncStrategy, MountRequest};
use std::path::PathBuf;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Example 1: Mount Context Hub as read-only filesystem
    let mount_request = MountRequest {
        mount_point: PathBuf::from("/Users/username/ContextHub"),
        sync_strategy: SyncStrategy::ReadOnly,
        folder_id: None, // Mount entire Context Hub
    };

    // Make API call to mount
    let client = reqwest::Client::new();
    let response = client
        .post("http://localhost:8080/api/mount")
        .json(&mount_request)
        .send()
        .await?;

    println!("Mount successful: {:?}", response.json::<serde_json::Value>().await?);

    // Now users can access Context Hub like a regular filesystem:
    // - Open /Users/username/ContextHub in Finder/Explorer
    // - Edit files in VSCode: code /Users/username/ContextHub
    // - Use command line: ls /Users/username/ContextHub

    // Example 2: Mount with bidirectional sync (like Dropbox)
    let sync_mount = MountRequest {
        mount_point: PathBuf::from("/Users/username/Documents/MyContextHub"),
        sync_strategy: SyncStrategy::Bidirectional,
        folder_id: Some("project-123".to_string()), // Mount specific folder
    };

    // Changes made in the filesystem will sync to Context Hub
    // Changes in Context Hub will appear in the filesystem

    // Example 3: Offline-first mode (sync every 5 minutes)
    let offline_mount = MountRequest {
        mount_point: PathBuf::from("/Users/username/OfflineHub"),
        sync_strategy: SyncStrategy::OfflineFirst {
            sync_interval: std::time::Duration::from_secs(300),
        },
        folder_id: None,
    };

    Ok(())
}

// CLI Usage Examples:
// 
// # Mount Context Hub
// context-hub mount ~/MyContextHub --sync bidirectional
//
// # Mount specific folder
// context-hub mount ~/Projects/lightning --folder-id project-123
//
// # List mounts
// context-hub mount list
//
// # Unmount
// context-hub unmount ~/MyContextHub
//
// # Status
// context-hub mount status ~/MyContextHub