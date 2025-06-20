# Timeline Scrubbing API Design

## Core Concept

A smooth, interactive timeline where users can drag to any point and instantly see the document state at that time. Change events appear as flags on the timeline for easy navigation.

## API Endpoints

### 1. Timeline Metadata

```rust
GET /api/timeline/info
Response: {
  "start_time": "2024-01-01T00:00:00Z",
  "end_time": "2024-01-20T15:30:00Z",
  "total_duration_ms": 1728000000,
  "snapshot_count": 456,
  "change_density": {
    // Buckets for UI to show activity heatmap
    "buckets": [
      {"start": 0, "end": 3600000, "change_count": 45},
      {"start": 3600000, "end": 7200000, "change_count": 12},
      // ... more buckets
    ],
    "bucket_size_ms": 3600000 // 1 hour buckets
  }
}

// Get change flags for timeline
GET /api/timeline/changes?resolution=hour
Response: {
  "changes": [
    {
      "timestamp": "2024-01-10T14:23:45Z",
      "offset_ms": 864225000, // ms from start
      "type": "document_created",
      "summary": "Added project README",
      "document_id": "abc123",
      "magnitude": "minor" // minor|moderate|major
    },
    {
      "timestamp": "2024-01-11T09:15:00Z", 
      "offset_ms": 932100000,
      "type": "bulk_update",
      "summary": "Updated 15 documents",
      "document_ids": ["def456", "ghi789", ...],
      "magnitude": "major"
    }
  ]
}
```

### 2. State at Timestamp

```rust
// Get exact state at any timestamp (optimized for scrubbing)
GET /api/timeline/state?timestamp=2024-01-10T14:30:00Z
Response: {
  "timestamp": "2024-01-10T14:30:00Z",
  "nearest_snapshot": {
    "id": "snapshot_123",
    "timestamp": "2024-01-10T14:00:00Z",
    "offset_ms": -1800000 // 30 min before requested time
  },
  "document_count": 145,
  "folder_structure": {
    "root": {
      "id": "root",
      "children": [
        {
          "id": "folder1",
          "name": "Projects",
          "document_count": 23,
          "last_modified": "2024-01-10T14:23:00Z"
        }
      ]
    }
  },
  "recent_changes": [
    // Changes since nearest snapshot
    {
      "timestamp": "2024-01-10T14:23:45Z",
      "type": "created",
      "document": { "id": "abc123", "name": "README.md" }
    }
  ]
}

// Efficient batch state retrieval for smooth scrubbing
POST /api/timeline/states
Request: {
  "timestamps": [
    "2024-01-10T14:00:00Z",
    "2024-01-10T14:15:00Z",
    "2024-01-10T14:30:00Z"
  ],
  "include_content": false // Just structure for performance
}
Response: {
  "states": [...]
}
```

### 3. WebSocket for Live Scrubbing

```typescript
// Connect for real-time updates during scrubbing
ws://localhost:3000/api/timeline/stream

// Client sends current scrub position
{
  "type": "scrub_position",
  "timestamp": "2024-01-10T14:30:00Z"
}

// Server streams state updates
{
  "type": "state_update",
  "timestamp": "2024-01-10T14:30:00Z",
  "changes_since_last": [
    {
      "document_id": "abc123",
      "change": "created",
      "name": "New Document"
    }
  ],
  "stats": {
    "total_documents": 145,
    "folders": 12
  }
}

// Preload hints for smooth scrubbing
{
  "type": "preload_hint",
  "timestamps": [
    "2024-01-10T14:45:00Z",
    "2024-01-10T15:00:00Z"
  ]
}
```

### 4. Document History Integration

```rust
// Get document state at specific time
GET /api/docs/{id}/at?timestamp=2024-01-10T14:30:00Z
Response: {
  "document": {
    "id": "abc123",
    "name": "README.md",
    "content": "...",
    "exists": true,
    "version_info": {
      "created_at": "2024-01-10T14:23:45Z",
      "last_modified": "2024-01-10T14:25:00Z",
      "snapshot_id": "snapshot_123"
    }
  }
}

// Get document lifecycle for timeline
GET /api/docs/{id}/lifecycle
Response: {
  "document_id": "abc123",
  "events": [
    {
      "timestamp": "2024-01-10T14:23:45Z",
      "type": "created",
      "offset_ms": 864225000
    },
    {
      "timestamp": "2024-01-10T16:00:00Z",
      "type": "modified",
      "offset_ms": 869400000,
      "change_size": "large"
    },
    {
      "timestamp": "2024-01-15T10:00:00Z",
      "type": "deleted",
      "offset_ms": 1296000000
    }
  ]
}
```

## Implementation Strategy

### 1. Snapshot Index for Fast Lookup

```rust
pub struct TimelineIndex {
    // B-tree for O(log n) timestamp lookups
    snapshots: BTreeMap<DateTime<Utc>, SnapshotRef>,
    
    // Change event index
    changes: BTreeMap<DateTime<Utc>, Vec<ChangeEvent>>,
    
    // Document lifecycle index
    document_lifecycles: HashMap<Uuid, DocumentLifecycle>,
}

impl TimelineIndex {
    pub fn find_nearest_snapshot(&self, timestamp: DateTime<Utc>) -> &SnapshotRef {
        self.snapshots
            .range(..=timestamp)
            .last()
            .map(|(_, snapshot)| snapshot)
            .unwrap_or_else(|| /* return oldest */)
    }
    
    pub fn get_changes_between(&self, start: DateTime<Utc>, end: DateTime<Utc>) -> Vec<&ChangeEvent> {
        self.changes
            .range(start..=end)
            .flat_map(|(_, events)| events)
            .collect()
    }
}
```

### 2. State Reconstruction Service

```rust
pub struct StateReconstructor {
    index: Arc<TimelineIndex>,
    snapshot_mgr: Arc<SnapshotManager>,
    cache: Arc<StateCache>,
}

impl StateReconstructor {
    pub async fn get_state_at(&self, timestamp: DateTime<Utc>) -> Result<DocumentState> {
        // Check cache first
        if let Some(state) = self.cache.get(&timestamp) {
            return Ok(state);
        }
        
        // Find nearest snapshot
        let nearest = self.index.find_nearest_snapshot(timestamp);
        let base_state = self.snapshot_mgr.load_snapshot(&nearest.id)?;
        
        // Apply changes since snapshot
        let changes = self.index.get_changes_between(nearest.timestamp, timestamp);
        let final_state = self.apply_changes(base_state, changes)?;
        
        // Cache for future requests
        self.cache.put(timestamp, final_state.clone());
        
        Ok(final_state)
    }
}
```

### 3. Change Detection System

```rust
pub struct ChangeDetector {
    pub async fn compute_timeline_changes(&self) -> Vec<TimelineChange> {
        let mut changes = Vec::new();
        let snapshots = self.snapshot_mgr.history(1000)?;
        
        for window in snapshots.windows(2) {
            let (prev, curr) = (&window[0], &window[1]);
            let diff = self.compute_diff(prev, curr)?;
            
            changes.extend(diff.into_timeline_changes());
        }
        
        changes
    }
}
```

## Client SDK

```typescript
import { TimelineClient } from '@context-hub/timeline';

const timeline = new TimelineClient('http://localhost:3000');

// Initialize timeline
const info = await timeline.getInfo();
const changes = await timeline.getChanges({ resolution: 'hour' });

// Scrub to position
const scrubber = timeline.createScrubber();
scrubber.on('state', (state) => {
  updateUI(state);
});

// Smooth scrubbing with preloading
await scrubber.scrubTo('2024-01-10T14:30:00Z');

// Jump to change
await scrubber.jumpToChange(changeId);

// Get document at time
const doc = await timeline.getDocumentAt(docId, timestamp);
```

## UI Component Example

```tsx
function Timeline() {
  const [position, setPosition] = useState(0);
  const [state, setState] = useState(null);
  const scrubber = useTimelineScrubber();
  
  const handleDrag = (newPosition: number) => {
    const timestamp = positionToTimestamp(newPosition);
    scrubber.scrubTo(timestamp);
    setPosition(newPosition);
  };
  
  return (
    <div className="timeline">
      <div className="timeline-track">
        {/* Activity heatmap background */}
        <ActivityHeatmap data={timeline.changeDensity} />
        
        {/* Change flags */}
        {changes.map(change => (
          <ChangeFlag 
            key={change.id}
            position={change.offset_ms / timeline.duration_ms}
            magnitude={change.magnitude}
            onClick={() => scrubber.jumpTo(change.timestamp)}
          />
        ))}
        
        {/* Scrubber handle */}
        <Scrubber 
          position={position}
          onDrag={handleDrag}
        />
      </div>
      
      {/* Current state display */}
      <StateDisplay state={state} />
    </div>
  );
}
```

## Performance Optimizations

1. **Snapshot Caching**
   - LRU cache for recently accessed snapshots
   - Preload adjacent snapshots during scrubbing

2. **Change Indexing**
   - Pre-compute and index all changes
   - Store in efficient binary format

3. **Progressive Loading**
   - Load document structure first
   - Fetch content on demand

4. **WebSocket Efficiency**
   - Batch updates during rapid scrubbing
   - Delta compression for state updates

5. **Time-based Sharding**
   - Partition timeline into time-based shards
   - Parallel loading of timeline segments