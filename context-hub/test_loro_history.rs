use loro::{LoroDoc, ExportMode};

fn main() {
    let doc = LoroDoc::new();
    
    // Check available methods
    println!("Loro methods exploration:");
    
    // Try to get version/history info
    let _map = doc.get_map("test");
    
    // Check if we can export with history
    let _snapshot = doc.export(ExportMode::Snapshot);
    let _updates = doc.export(ExportMode::Updates { from: None });
    
    // Check for version/oplog/history methods
    // The actual methods will be revealed by IDE/compiler
}