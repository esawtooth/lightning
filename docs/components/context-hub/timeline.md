# Context Hub Timeline System

The Timeline system provides chronological event storage, replay, and scrubbing capabilities for the Context Hub.

## Overview

The Timeline system captures all document operations and state changes as a sequence of timestamped events. This enables:

- **Event Replay**: Reconstruct system state at any point in time
- **Timeline Scrubbing**: Navigate through time like a video player
- **Audit Logging**: Complete history of all changes
- **Debugging**: Replay specific sequences to diagnose issues

## Event Structure

Each timeline event contains:

```rust
pub struct TimelineEvent {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    pub event_type: String,
    pub document_id: Option<String>,
    pub user_id: Option<String>,
    pub data: serde_json::Value,
    pub metadata: HashMap<String, String>,
}
```

## Event Types

### Document Events
- `document.created` - Document created
- `document.updated` - Document modified
- `document.deleted` - Document removed
- `document.indexed` - Document added to search index

### System Events
- `system.startup` - Context Hub started
- `system.shutdown` - Context Hub stopped
- `system.backup` - Backup created
- `system.restore` - Backup restored

### User Events
- `user.login` - User authenticated
- `user.logout` - User session ended
- `user.action` - User performed action

## API Operations

### Get Timeline Events
```http
GET /timeline?start=2023-01-01T00:00:00Z&end=2023-01-02T00:00:00Z&limit=100
```

Parameters:
- `start` - Start timestamp (ISO 8601)
- `end` - End timestamp (ISO 8601)
- `limit` - Maximum events to return (default: 100)
- `event_types` - Filter by event types (comma-separated)
- `document_id` - Filter by document ID
- `user_id` - Filter by user ID

### Scrub to Timestamp
```http
POST /timeline/scrub
Content-Type: application/json

{
  "timestamp": "2023-01-01T12:00:00Z",
  "preview": false
}
```

This reconstructs the system state as it existed at the specified timestamp.

### Replay Events
```http
POST /timeline/replay
Content-Type: application/json

{
  "from": "2023-01-01T00:00:00Z",
  "to": "2023-01-01T12:00:00Z",
  "speed": 1.0,
  "event_types": ["document.created", "document.updated"]
}
```

This replays events in chronological order, optionally at faster/slower speeds.

## WebSocket Streaming

### Real-time Timeline Events
```javascript
const ws = new WebSocket('ws://localhost:3000/timeline/stream');

ws.onmessage = (event) => {
  const timelineEvent = JSON.parse(event.data);
  console.log('New timeline event:', timelineEvent);
};
```

### Timeline Scrubbing
```javascript
const ws = new WebSocket('ws://localhost:3000/timeline/scrub');

// Send scrub command
ws.send(JSON.stringify({
  timestamp: "2023-01-01T12:00:00Z"
}));

// Receive state changes
ws.onmessage = (event) => {
  const stateChange = JSON.parse(event.data);
  console.log('State change:', stateChange);
};
```

## Storage and Performance

### Storage Format
- Events stored in append-only log format
- Indexed by timestamp for fast range queries
- Compressed using zstd for space efficiency

### Performance Characteristics
- Write throughput: 10,000+ events/second
- Query latency: <10ms for range queries
- Storage efficiency: ~100 bytes per event (compressed)

### Retention Policies
- Events older than 30 days compressed
- Events older than 1 year archived to cold storage
- Critical events never deleted

## Implementation Details

### Event Ordering
Events are ordered by:
1. Timestamp (primary)
2. Event ID (secondary, for deterministic ordering)

### Conflict Resolution
For concurrent events with identical timestamps:
- Use event ID for deterministic ordering
- Apply CRDT merge rules for document conflicts

### Snapshots
Periodic snapshots reduce replay time:
- Full system snapshots every hour
- Incremental snapshots every 10 minutes
- Snapshots compressed and checksummed

## Usage Examples

### Debugging Document Changes
```bash
# Get all events for a specific document
curl "http://localhost:3000/timeline?document_id=doc-123"

# Replay events to see how document evolved
curl -X POST "http://localhost:3000/timeline/replay" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "doc-123", "from": "2023-01-01T00:00:00Z"}'
```

### System State Recovery
```bash
# Scrub to state before incident
curl -X POST "http://localhost:3000/timeline/scrub" \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2023-01-01T11:59:00Z"}'

# Create backup of recovered state
curl -X POST "http://localhost:3000/snapshots" \
  -H "Content-Type: application/json" \
  -d '{"name": "pre-incident-recovery"}'
```

### Performance Monitoring
```bash
# Get recent system events
curl "http://localhost:3000/timeline?event_types=system.startup,system.shutdown&limit=10"

# Stream real-time events
wscat -c ws://localhost:3000/timeline/stream
```