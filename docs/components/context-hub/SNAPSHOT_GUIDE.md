# Context Hub Snapshot System Guide

## Overview

The Context Hub implements a Git-based snapshot system for CRDT document persistence and time-travel capabilities. Snapshots provide durability, versioning, and the ability to restore the system to any previous state.

## Architecture

### Core Components

1. **SnapshotManager** (`context-hub-core/src/snapshot.rs`)
   - Manages a Git repository for storing document snapshots
   - Provides APIs for creating, listing, and restoring from snapshots
   - Supports both commit hashes and RFC3339 timestamps for restoration

2. **Document Storage Format**
   - Documents are stored as binary files using Loro CRDT format
   - Each document is saved as `{uuid}.bin` in the snapshot repository
   - Uses `loro::ExportMode::Snapshot` for efficient storage

3. **Snapshot Repository Structure**
   ```
   snapshots/
   ├── .git/              # Git repository metadata
   ├── {uuid1}.bin        # Document 1
   ├── {uuid2}.bin        # Document 2
   └── ...                # More documents
   ```

## Key Features

### 1. Automatic Snapshots
The system automatically creates snapshots:
- Default interval: Every hour (3600 seconds)
- Configurable via `SNAPSHOT_INTERVAL_SECS` environment variable
- Only snapshots when documents have been modified (dirty state)

### 2. Snapshot Creation Process
```rust
// From snapshot.rs
pub fn snapshot(&self, store: &DocumentStore) -> Result<Oid> {
    // 1. Copy all document files to git working directory
    // 2. Stage all changes
    // 3. Create commit with timestamp
    // 4. Tag with "snapshot-{timestamp}"
    // 5. Return commit ID
}
```

### 3. Snapshot Retention
- Configurable via `SNAPSHOT_RETENTION` environment variable
- Automatically prunes old snapshot tags to maintain the specified number
- Keeps the most recent snapshots

### 4. Time Travel Capabilities

#### Load Specific Document from History
```rust
// Load a document as it existed at a specific revision
let doc = snapshot_mgr.load_document_at(doc_id, "commit_hash")?;

// Or use a timestamp
let doc = snapshot_mgr.load_document_at(doc_id, "2024-06-19T10:30:00Z")?;
```

#### Restore Entire Store
```rust
// Restore to a specific commit
snapshot_mgr.restore(&mut store, "abc123def")?;

// Restore to a timestamp (finds latest commit before that time)
snapshot_mgr.restore(&mut store, "2024-06-19T10:30:00Z")?;
```

### 5. History Inspection
```rust
// Get list of recent snapshots
let history = snapshot_mgr.history(10)?; // Last 10 snapshots
for snapshot in history {
    println!("Commit: {} at {}", snapshot.id, snapshot.time);
}
```

## Document Structure

Documents are stored using the Loro CRDT format with the following metadata:
- `meta/doc_type`: Document type (Text, Folder, IndexGuide)
- `meta/owner`: Document owner
- `meta/name`: Document name
- `meta/parent_folder_id`: Optional parent folder UUID
- `content`: List of content items (for Text/IndexGuide types)
- `children`: Map of child documents (for Folder type)

## API Integration

While the current implementation doesn't expose HTTP endpoints for snapshots, the system is designed to support:
- `POST /snapshot` - Trigger manual snapshot
- `GET /snapshots` - List available snapshots
- `GET /snapshots/{rev}/docs/{id}` - Get document from specific snapshot
- `POST /restore/{rev}` - Restore to specific snapshot

## Environment Variables

- `SNAPSHOT_DIR`: Directory for Git repository (default: "snapshots")
- `SNAPSHOT_INTERVAL_SECS`: Seconds between automatic snapshots (default: 3600)
- `SNAPSHOT_RETENTION`: Number of snapshots to keep (optional)

## Usage Examples

### 1. Reading Snapshot History
```rust
use context_hub_core::snapshot::SnapshotManager;

let mgr = SnapshotManager::new("snapshots")?;
let history = mgr.history(10)?;
for snapshot in history {
    println!("{}: {}", snapshot.time, snapshot.id);
}
```

### 2. Comparing Document Versions
```rust
// Get current version
let current = store.get(doc_id)?;

// Get version from yesterday
let yesterday = chrono::Utc::now() - chrono::Duration::days(1);
let old_doc = mgr.load_document_at(doc_id, &yesterday.to_rfc3339())?;

// Compare content
if let (Some(current), Some(old)) = (current, old_doc) {
    println!("Current: {}", current.text());
    println!("Yesterday: {}", old.text());
}
```

### 3. Disaster Recovery
```rust
// In case of data corruption, restore from last known good snapshot
let history = mgr.history(1)?;
if let Some(latest) = history.first() {
    mgr.restore(&mut store, &latest.id.to_string())?;
    println!("Restored to {}", latest.time);
}
```

## Best Practices

1. **Regular Snapshots**: Keep the default hourly snapshots for production systems
2. **Retention Policy**: Set appropriate retention based on storage capacity and recovery needs
3. **Manual Snapshots**: Create manual snapshots before major operations
4. **Monitoring**: Monitor snapshot creation to ensure they're happening regularly
5. **Testing**: Regularly test restoration procedures

## Limitations

1. Snapshots are full copies (not incremental) - may use significant disk space
2. Git operations are synchronous - may impact performance during snapshot creation
3. No built-in remote backup - consider pushing the Git repository to a remote

## Future Enhancements

1. Incremental snapshots using Git's delta compression
2. Remote snapshot repositories for distributed backup
3. Snapshot diffing and visualization tools
4. Integration with CI/CD for automated testing of snapshots