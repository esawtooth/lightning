# Context Hub

Context Hub is a Rust-based persistent storage service that provides CRDT (Conflict-free Replicated Data Type) synchronization and timeline management for Lightning OS.

## Features

- **Document Storage**: Persistent document storage with versioning
- **CRDT Synchronization**: Conflict-free replication across distributed nodes
- **Timeline System**: Event timeline with scrubbing and replay capabilities
- **Search Indexing**: Full-text search with Tantivy
- **Snapshot Management**: Point-in-time snapshots for recovery
- **RESTful API**: HTTP API for all operations

## Architecture

### Core Components

- **Storage Engine**: Persistent document storage
- **CRDT Engine**: Conflict resolution and synchronization
- **Timeline Manager**: Event ordering and replay
- **Search Index**: Full-text search capabilities
- **Snapshot Manager**: Backup and recovery

### Data Models

- **Documents**: JSON documents with metadata
- **Events**: Timeline events with timestamps
- **Snapshots**: Point-in-time system state
- **Indices**: Search index entries

## API Endpoints

### Documents
- `POST /documents` - Create document
- `GET /documents/{id}` - Get document
- `PUT /documents/{id}` - Update document
- `DELETE /documents/{id}` - Delete document

### Timeline
- `GET /timeline` - Get timeline events
- `POST /timeline/scrub` - Scrub to specific time
- `POST /timeline/replay` - Replay events

### Search
- `GET /search?q={query}` - Search documents
- `POST /index` - Rebuild search index

### Snapshots
- `POST /snapshots` - Create snapshot
- `GET /snapshots` - List snapshots
- `POST /snapshots/{id}/restore` - Restore snapshot

## Configuration

Environment variables:
- `CONTEXT_HUB_PORT` - HTTP server port (default: 3000)
- `CONTEXT_HUB_DATA_DIR` - Data directory path
- `CONTEXT_HUB_LOG_LEVEL` - Logging level

## Development

### Build
```bash
cd context-hub
cargo build --release
```

### Run
```bash
cargo run
```

### Test
```bash
cargo test
```

### Benchmarks
```bash
cargo bench
```

## Integration

Context Hub integrates with Lightning Core through:
- HTTP API calls for document operations
- Event timeline synchronization
- Search index updates
- Snapshot-based recovery

## Deployment

### Docker
```bash
docker build -t context-hub .
docker run -p 3000:3000 context-hub
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: context-hub
spec:
  replicas: 1
  selector:
    matchLabels:
      app: context-hub
  template:
    metadata:
      labels:
        app: context-hub
    spec:
      containers:
      - name: context-hub
        image: context-hub:latest
        ports:
        - containerPort: 3000
```