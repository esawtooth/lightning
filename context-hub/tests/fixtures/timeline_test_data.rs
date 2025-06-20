use chrono::{DateTime, Utc, TimeZone};
use context_hub_core::{
    timeline::{TimelineChange, ChangeType, ChangeMagnitude},
    snapshot::SnapshotManager,
    storage::crdt::{DocumentStore, DocumentType},
};
use std::path::Path;
use uuid::Uuid;

/// Create a test timestamp from seconds since epoch
pub fn test_timestamp(secs: i64) -> DateTime<Utc> {
    Utc.timestamp_opt(secs, 0).unwrap()
}

/// Generate a series of test snapshots with documents
pub async fn create_test_snapshots(
    snapshot_dir: &Path,
    data_dir: &Path,
    num_snapshots: usize,
    docs_per_snapshot: usize,
) -> anyhow::Result<Vec<(String, DateTime<Utc>)>> {
    let snapshot_mgr = SnapshotManager::new(snapshot_dir)?;
    let mut store = DocumentStore::new(data_dir)?;
    let mut snapshots = Vec::new();
    
    for i in 0..num_snapshots {
        // Add new documents
        for j in 0..docs_per_snapshot {
            let doc_id = Uuid::new_v4();
            store.create(
                doc_id,
                "test_user",
                &format!("Document_{}_{}", i, j),
                &format!("Content for snapshot {} document {}", i, j),
                None,
                DocumentType::Document,
            )?;
        }
        
        // Modify some existing documents
        if i > 0 {
            for (id, doc) in store.iter().take(2) {
                store.update(*id, &format!("{} - Modified in snapshot {}", doc.text(), i))?;
            }
        }
        
        // Take snapshot
        let snapshot_id = snapshot_mgr.snapshot(&store)?;
        let timestamp = Utc::now() + chrono::Duration::seconds(i as i64 * 3600);
        
        snapshots.push((snapshot_id.to_string(), timestamp));
        
        // Small delay to ensure different timestamps
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }
    
    Ok(snapshots)
}

/// Generate test timeline changes
pub fn generate_test_changes(
    start_time: DateTime<Utc>,
    num_changes: usize,
    interval_secs: i64,
) -> Vec<TimelineChange> {
    let mut changes = Vec::new();
    
    for i in 0..num_changes {
        let timestamp = start_time + chrono::Duration::seconds(i as i64 * interval_secs);
        
        let (change_type, magnitude, doc_count) = match i % 5 {
            0 => (ChangeType::DocumentCreated, ChangeMagnitude::Minor, 1),
            1 => (ChangeType::DocumentModified, ChangeMagnitude::Minor, 1),
            2 => (ChangeType::DocumentDeleted, ChangeMagnitude::Minor, 1),
            3 => (ChangeType::BulkUpdate, ChangeMagnitude::Moderate, 5),
            4 => (ChangeType::FolderCreated, ChangeMagnitude::Major, 10),
            _ => unreachable!(),
        };
        
        let document_ids: Vec<Uuid> = (0..doc_count).map(|_| Uuid::new_v4()).collect();
        
        changes.push(TimelineChange {
            timestamp,
            offset_ms: timestamp.timestamp_millis(),
            change_type,
            summary: format!("Test change {}", i),
            document_ids,
            magnitude,
        });
    }
    
    changes
}

/// Create a complex document hierarchy for testing
pub fn create_document_hierarchy(store: &mut DocumentStore) -> anyhow::Result<Vec<Uuid>> {
    let mut doc_ids = Vec::new();
    
    // Create folders
    let root_folder = Uuid::new_v4();
    store.create(
        root_folder,
        "test_user",
        "Root Folder",
        "",
        None,
        DocumentType::Folder,
    )?;
    doc_ids.push(root_folder);
    
    // Create subfolders
    for i in 0..3 {
        let subfolder = Uuid::new_v4();
        store.create(
            subfolder,
            "test_user",
            &format!("Subfolder {}", i),
            "",
            Some(root_folder),
            DocumentType::Folder,
        )?;
        doc_ids.push(subfolder);
        
        // Create documents in subfolder
        for j in 0..5 {
            let doc = Uuid::new_v4();
            store.create(
                doc,
                "test_user",
                &format!("Document {}_{}", i, j),
                &format!("Content for document {} in subfolder {}", j, i),
                Some(subfolder),
                DocumentType::Document,
            )?;
            doc_ids.push(doc);
        }
    }
    
    // Create some root-level documents
    for i in 0..5 {
        let doc = Uuid::new_v4();
        store.create(
            doc,
            "test_user",
            &format!("Root Document {}", i),
            &format!("Content for root document {}", i),
            None,
            DocumentType::Document,
        )?;
        doc_ids.push(doc);
    }
    
    Ok(doc_ids)
}

/// Simulate realistic document changes over time
pub fn simulate_document_evolution(
    store: &mut DocumentStore,
    doc_ids: &[Uuid],
    num_changes: usize,
) -> anyhow::Result<Vec<TimelineChange>> {
    let mut changes = Vec::new();
    let start_time = Utc::now();
    
    for i in 0..num_changes {
        let timestamp = start_time + chrono::Duration::minutes(i as i64 * 5);
        
        match i % 4 {
            0 => {
                // Create new document
                let doc_id = Uuid::new_v4();
                let parent = if i % 2 == 0 { None } else { Some(doc_ids[0]) };
                
                store.create(
                    doc_id,
                    "test_user",
                    &format!("New Document {}", i),
                    &format!("Created at change {}", i),
                    parent,
                    DocumentType::Document,
                )?;
                
                changes.push(TimelineChange {
                    timestamp,
                    offset_ms: timestamp.timestamp_millis(),
                    change_type: ChangeType::DocumentCreated,
                    summary: format!("Created 'New Document {}'", i),
                    document_ids: vec![doc_id],
                    magnitude: ChangeMagnitude::Minor,
                });
            }
            1 => {
                // Modify existing document
                let doc_id = doc_ids[i % doc_ids.len()];
                store.update(doc_id, &format!("Updated content at change {}", i))?;
                
                changes.push(TimelineChange {
                    timestamp,
                    offset_ms: timestamp.timestamp_millis(),
                    change_type: ChangeType::DocumentModified,
                    summary: format!("Modified document"),
                    document_ids: vec![doc_id],
                    magnitude: ChangeMagnitude::Minor,
                });
            }
            2 => {
                // Bulk update
                let update_count = 5.min(doc_ids.len());
                let mut updated_ids = Vec::new();
                
                for j in 0..update_count {
                    let doc_id = doc_ids[(i + j) % doc_ids.len()];
                    store.update(doc_id, &format!("Bulk update {} at change {}", j, i))?;
                    updated_ids.push(doc_id);
                }
                
                changes.push(TimelineChange {
                    timestamp,
                    offset_ms: timestamp.timestamp_millis(),
                    change_type: ChangeType::BulkUpdate,
                    summary: format!("Updated {} documents", update_count),
                    document_ids: updated_ids,
                    magnitude: ChangeMagnitude::Moderate,
                });
            }
            3 => {
                // Delete document (if we have extras)
                if doc_ids.len() > 10 && i < doc_ids.len() {
                    let doc_id = doc_ids[doc_ids.len() - 1 - (i % 5)];
                    store.delete(doc_id)?;
                    
                    changes.push(TimelineChange {
                        timestamp,
                        offset_ms: timestamp.timestamp_millis(),
                        change_type: ChangeType::DocumentDeleted,
                        summary: format!("Deleted document"),
                        document_ids: vec![doc_id],
                        magnitude: ChangeMagnitude::Minor,
                    });
                }
            }
            _ => unreachable!(),
        }
    }
    
    Ok(changes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    
    #[test]
    fn test_timestamp_generation() {
        let ts = test_timestamp(1000);
        assert_eq!(ts.timestamp(), 1000);
    }
    
    #[test]
    fn test_change_generation() {
        let start = Utc::now();
        let changes = generate_test_changes(start, 10, 60);
        
        assert_eq!(changes.len(), 10);
        
        // Verify change types cycle correctly
        assert!(matches!(changes[0].change_type, ChangeType::DocumentCreated));
        assert!(matches!(changes[1].change_type, ChangeType::DocumentModified));
        assert!(matches!(changes[2].change_type, ChangeType::DocumentDeleted));
        assert!(matches!(changes[3].change_type, ChangeType::BulkUpdate));
        assert!(matches!(changes[4].change_type, ChangeType::FolderCreated));
        
        // Verify timestamps increment correctly
        for i in 1..changes.len() {
            let diff = changes[i].timestamp - changes[i-1].timestamp;
            assert_eq!(diff.num_seconds(), 60);
        }
    }
    
    #[test]
    fn test_document_hierarchy() {
        let temp_dir = TempDir::new().unwrap();
        let mut store = DocumentStore::new(temp_dir.path()).unwrap();
        
        let doc_ids = create_document_hierarchy(&mut store).unwrap();
        
        // Should have 1 root folder + 3 subfolders + 15 docs in subfolders + 5 root docs = 24
        assert_eq!(doc_ids.len(), 24);
        
        // Verify folder structure
        let folders: Vec<_> = store.iter()
            .filter(|(_, doc)| doc.doc_type() == DocumentType::Folder)
            .collect();
        assert_eq!(folders.len(), 4); // 1 root + 3 subfolders
    }
}