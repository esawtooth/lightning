use context_hub_core::{
    snapshot::SnapshotManager,
    storage::crdt::DocumentStore,
};
use std::path::Path;
use uuid::Uuid;

fn main() -> anyhow::Result<()> {
    // Example of reading snapshots from the context-hub
    
    // 1. Initialize the snapshot manager with the snapshots directory
    let snapshot_dir = Path::new("snapshots");
    let snapshot_mgr = SnapshotManager::new(snapshot_dir)?;
    
    // 2. List available snapshots
    println!("=== Available Snapshots ===");
    let history = snapshot_mgr.history(10)?;
    
    if history.is_empty() {
        println!("No snapshots found in the repository.");
        println!("\nTo create snapshots:");
        println!("1. The context-hub server automatically creates snapshots periodically");
        println!("2. You can trigger a manual snapshot via the API");
        return Ok(());
    }
    
    for (i, snapshot) in history.iter().enumerate() {
        println!("{}. Commit: {} - Time: {}", 
            i + 1, 
            &snapshot.id.to_string()[..8], 
            snapshot.time.format("%Y-%m-%d %H:%M:%S UTC")
        );
    }
    
    // 3. Example: Load a specific document from a snapshot
    // You would need to know the document UUID
    let example_doc_id = Uuid::parse_str("7775f9ba-9232-4703-b3cd-d4e515b332f3")?; // Example from data dir
    
    if let Some(first_snapshot) = history.first() {
        println!("\n=== Loading Document from Snapshot ===");
        println!("Snapshot: {}", &first_snapshot.id.to_string()[..8]);
        
        match snapshot_mgr.load_document_at(example_doc_id, &first_snapshot.id.to_string()) {
            Ok(Some(doc)) => {
                println!("Document found!");
                println!("  ID: {}", doc.id());
                println!("  Name: {}", doc.name());
                println!("  Owner: {}", doc.owner());
                println!("  Type: {:?}", doc.doc_type());
                println!("  Content preview: {}", 
                    doc.text().chars().take(100).collect::<String>()
                );
            }
            Ok(None) => {
                println!("Document {} not found in this snapshot", example_doc_id);
            }
            Err(e) => {
                println!("Error loading document: {}", e);
            }
        }
    }
    
    // 4. Example: Restore entire document store from a snapshot
    println!("\n=== Restoring from Snapshot ===");
    if let Some(snapshot) = history.first() {
        let data_dir = Path::new("restored_data");
        std::fs::create_dir_all(data_dir)?;
        
        let mut store = DocumentStore::new(data_dir)?;
        
        println!("Restoring from snapshot: {}", &snapshot.id.to_string()[..8]);
        snapshot_mgr.restore(&mut store, &snapshot.id.to_string())?;
        
        println!("Restored documents:");
        for (id, _) in store.list() {
            if let Ok(Some(doc)) = store.get(*id) {
                println!("  - {} ({})", doc.name(), id);
            }
        }
        
        // Clean up
        std::fs::remove_dir_all(data_dir)?;
    }
    
    // 5. Working with timestamps
    println!("\n=== Snapshot by Timestamp ===");
    if !history.is_empty() {
        // You can also restore to a specific point in time
        let timestamp = history[0].time.to_rfc3339();
        println!("Snapshot at timestamp: {}", timestamp);
        
        // The restore method accepts RFC3339 timestamps
        // snapshot_mgr.restore(&mut store, &timestamp)?;
    }
    
    Ok(())
}