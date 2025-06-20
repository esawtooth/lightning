# Timeline API Usage Guide

## Overview

The Timeline API has been implemented with the following endpoints:

### 1. Timeline Information
```bash
GET /timeline/info
```
Returns timeline metadata including start/end times, snapshot count, and activity density buckets.

### 2. Timeline Changes
```bash
GET /timeline/changes?resolution=hour
```
Returns all change events with timestamps and metadata for placing flags on the timeline.

### 3. State at Timestamp
```bash
GET /timeline/state?timestamp=2024-01-10T14:30:00Z
```
Returns the document store state at any given timestamp, perfect for drag/drop scrubbing.

### 4. WebSocket Streaming
```bash
ws://localhost:3000/timeline/stream
```
Real-time state updates during scrubbing for smooth UI interactions.

## Client Example

```javascript
// Initialize timeline
const timelineInfo = await fetch('/timeline/info').then(r => r.json());
const changes = await fetch('/timeline/changes').then(r => r.json());

// Scrub to specific time
async function scrubToTime(timestamp) {
  const state = await fetch(`/timeline/state?timestamp=${timestamp}`)
    .then(r => r.json());
  updateUI(state);
}

// WebSocket for smooth scrubbing
const ws = new WebSocket('ws://localhost:3000/timeline/stream');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'state_update') {
    updateUISmooth(data);
  }
};

// Send scrub position
function handleTimelineDrag(timestamp) {
  ws.send(JSON.stringify({
    type: 'scrub_position',
    timestamp: timestamp
  }));
}
```

## Testing

Run the test script:
```bash
./test_timeline.sh
```

Or test individual endpoints:
```bash
# Get timeline info
curl http://localhost:3000/timeline/info | jq .

# Get changes
curl http://localhost:3000/timeline/changes | jq .

# Get state at specific time
curl "http://localhost:3000/timeline/state?timestamp=2024-01-20T10:00:00Z" | jq .
```

## Implementation Details

- **Efficient Indexing**: B-tree structure for O(log n) timestamp lookups
- **Change Detection**: Tracks document additions, modifications, and deletions
- **State Reconstruction**: Loads nearest snapshot and applies changes
- **Caching**: LRU cache for frequently accessed states
- **WebSocket Support**: Real-time updates during timeline scrubbing

## Next Steps

1. Implement actual change detection between snapshots (currently using synthetic data)
2. Add document-level change tracking
3. Optimize for large-scale deployments with thousands of snapshots
4. Add timeline export/replay recording functionality