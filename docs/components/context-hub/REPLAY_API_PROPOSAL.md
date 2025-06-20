# Context Hub Replay API Proposal

## Overview

The replay functionality will allow users to visualize changes to documents over time, providing an intuitive way to understand how the document store evolved. The API will leverage the existing Git-based snapshot system while adding new capabilities for change tracking and streaming updates.

## API Design

### 1. Timeline Endpoints

```rust
// Get available snapshot timeline
GET /api/replay/timeline
Response: {
  "snapshots": [
    {
      "id": "abc123",
      "timestamp": "2024-01-20T10:00:00Z",
      "commit_message": "Hourly snapshot",
      "document_count": 150,
      "total_size_bytes": 2048000
    }
  ],
  "start_time": "2024-01-01T00:00:00Z",
  "end_time": "2024-01-20T12:00:00Z"
}

// Get changes between two snapshots
GET /api/replay/changes?from={snapshot_id}&to={snapshot_id}
Response: {
  "added": ["doc_id_1", "doc_id_2"],
  "modified": ["doc_id_3", "doc_id_4"],
  "deleted": ["doc_id_5"],
  "total_changes": 5
}
```

### 2. Replay Session Endpoints

```rust
// Create a replay session
POST /api/replay/sessions
Request: {
  "start_snapshot": "snapshot_id_or_timestamp",
  "end_snapshot": "snapshot_id_or_timestamp", // optional, defaults to latest
  "speed": 1.0, // playback speed multiplier
  "granularity": "snapshot" // or "operation" for fine-grained replay
}
Response: {
  "session_id": "replay_123",
  "websocket_url": "/api/replay/sessions/replay_123/stream"
}

// Control replay session
POST /api/replay/sessions/{session_id}/control
Request: {
  "action": "play" | "pause" | "seek" | "step_forward" | "step_backward",
  "position": "snapshot_id" // for seek action
}

// Get replay session state
GET /api/replay/sessions/{session_id}
Response: {
  "status": "playing" | "paused" | "completed",
  "current_snapshot": "snapshot_id",
  "current_timestamp": "2024-01-20T10:00:00Z",
  "progress": 0.75,
  "document_state": {
    "count": 150,
    "folders": [...]
  }
}
```

### 3. WebSocket Streaming

```typescript
// Connect to replay stream
ws://localhost:3000/api/replay/sessions/{session_id}/stream

// Incoming messages
{
  "type": "snapshot_change",
  "snapshot_id": "abc123",
  "timestamp": "2024-01-20T10:00:00Z",
  "changes": {
    "added": [
      {
        "id": "doc_id_1",
        "name": "New Document",
        "type": "document",
        "content_preview": "First 100 chars..."
      }
    ],
    "modified": [...],
    "deleted": [...]
  }
}

// For fine-grained replay (operation level)
{
  "type": "operation",
  "timestamp": "2024-01-20T10:00:00.123Z",
  "operation": {
    "type": "insert_text",
    "document_id": "doc_id_1",
    "position": 42,
    "text": "Hello"
  }
}
```

### 4. Document History Endpoints

```rust
// Get history for specific document
GET /api/docs/{id}/history
Response: {
  "document_id": "doc_id",
  "versions": [
    {
      "snapshot_id": "abc123",
      "timestamp": "2024-01-20T10:00:00Z",
      "size_bytes": 1024,
      "change_summary": "Added section on API design"
    }
  ]
}

// Compare document versions
GET /api/docs/{id}/diff?from={snapshot_id}&to={snapshot_id}
Response: {
  "document_id": "doc_id",
  "from_snapshot": "abc123",
  "to_snapshot": "def456",
  "diff": {
    "type": "unified", // or "semantic" for structural diffs
    "changes": [...]
  }
}
```

## Implementation Approach

### Phase 1: Core Infrastructure (Week 1-2)

1. **Replay State Manager**
   ```rust
   pub struct ReplaySession {
       id: Uuid,
       start_snapshot: String,
       end_snapshot: String,
       current_position: String,
       speed: f32,
       status: ReplayStatus,
       subscribers: Vec<WebSocketConnection>,
   }
   ```

2. **Change Detection Service**
   - Efficient diff computation between snapshots
   - Cache frequently accessed diffs
   - Support for both document-level and content-level changes

3. **WebSocket Infrastructure**
   - Add WebSocket support to Axum server
   - Implement message broadcasting for replay events
   - Handle connection lifecycle and cleanup

### Phase 2: API Implementation (Week 2-3)

1. **HTTP Endpoints**
   - Implement all REST endpoints
   - Add proper error handling and validation
   - Include authentication/authorization

2. **Replay Engine**
   ```rust
   pub struct ReplayEngine {
       snapshot_manager: Arc<SnapshotManager>,
       sessions: Arc<RwLock<HashMap<Uuid, ReplaySession>>>,
       change_cache: Arc<ChangeCache>,
   }
   ```

3. **Streaming Logic**
   - Timer-based progression for "play" mode
   - Event queuing for smooth playback
   - Support for different playback speeds

### Phase 3: Optimizations (Week 3-4)

1. **Performance**
   - Implement change caching
   - Add pagination for large change sets
   - Optimize Git operations for faster snapshot access

2. **Advanced Features**
   - Fine-grained CRDT operation replay
   - Document content diffing with semantic understanding
   - Export replay as video/GIF

## Client SDK Example

```typescript
import { ReplayClient } from '@context-hub/replay';

const client = new ReplayClient('http://localhost:3000');

// Create and control replay
const session = await client.createSession({
  startTime: '2024-01-01T00:00:00Z',
  endTime: '2024-01-20T00:00:00Z',
  speed: 2.0
});

// Subscribe to changes
session.on('change', (event) => {
  console.log(`${event.changes.added.length} documents added`);
  updateUI(event.changes);
});

// Control playback
await session.play();
await session.pause();
await session.seek('2024-01-10T00:00:00Z');

// Get document history
const history = await client.getDocumentHistory('doc_id');
const diff = await client.compareVersions('doc_id', 'v1', 'v2');
```

## UI Integration Ideas

1. **Timeline Scrubber**
   - Visual timeline with snapshot markers
   - Drag to seek, click to jump
   - Show activity heatmap

2. **Change Visualization**
   - Animated document tree showing additions/deletions
   - Side-by-side comparison view
   - Activity feed of changes

3. **Playback Controls**
   - Play/pause/step buttons
   - Speed control slider
   - Jump to next/previous change

## Technical Considerations

1. **Scalability**
   - Limit concurrent replay sessions
   - Implement session timeout
   - Consider Redis for session state in distributed setup

2. **Storage**
   - Cache computed diffs
   - Consider S3/blob storage for large snapshots
   - Implement snapshot compression

3. **Security**
   - Ensure replay respects original access controls
   - Add rate limiting for expensive operations
   - Audit log for replay access

## Migration Path

1. No breaking changes to existing APIs
2. Replay features are additive
3. Gradual rollout with feature flags
4. Backward compatibility with existing snapshots