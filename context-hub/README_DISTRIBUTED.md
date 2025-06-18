# Context Hub - Distributed Architecture

A production-ready, distributed document storage system with CRDT support, designed for horizontal scalability and high availability.

## Architecture Overview

Context Hub has been redesigned from a single-node proof-of-concept to a distributed, production-ready system capable of handling millions of users and documents.

### Key Improvements

1. **Horizontal Scalability**: User-based sharding with consistent hashing
2. **High Availability**: 3-way replication with automatic failover
3. **Durability**: Write-ahead log with continuous S3 archival
4. **Security**: End-to-end encryption, JWT auth with refresh tokens
5. **Performance**: Multi-tier caching, connection pooling, async I/O

## System Components

### 1. API Gateway Layer
- Load balances requests across shards
- Routes based on user ID using consistent hashing
- Implements rate limiting and DDoS protection
- Handles authentication and token refresh

### 2. Shard Nodes
Each shard handles a subset of users and includes:
- **Write-Ahead Log (WAL)**: Durability for all operations
- **CRDT Engine**: Conflict-free collaborative editing
- **Redis Cache**: Hot data with sub-ms latency
- **PostgreSQL**: Document metadata and ACLs
- **S3 Storage**: Document content and attachments

### 3. Cluster Coordinator (etcd)
- Service discovery and health monitoring
- Distributed configuration management
- Leader election for shard primaries
- Distributed locking for coordination

### 4. Background Services
- WAL compaction and archival
- Dead shard detection and rebalancing
- Metrics collection and alerting
- Audit log aggregation

## Deployment

### Prerequisites

- Kubernetes cluster (or Docker Swarm)
- PostgreSQL 14+ with Citus extension
- Redis 7+ cluster
- etcd 3.5+ cluster
- S3-compatible storage (MinIO or AWS S3)
- Elasticsearch 8+ cluster (optional, for search)

### Environment Variables

```bash
# Cluster coordination
ETCD_ENDPOINTS=http://etcd-0:2379,http://etcd-1:2379,http://etcd-2:2379

# Data storage
DATABASE_URL=postgres://user:pass@postgres:5432/contexthub
REDIS_URL=redis://redis-cluster:6379

# Object storage
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=context-hub-prod
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# Security
MASTER_KEY=base64_encoded_32_byte_key
JWT_SECRET=your-jwt-secret

# Performance tuning
CACHE_SIZE_MB=1024
CONNECTION_POOL_SIZE=20
WAL_SEGMENT_SIZE_MB=128
```

### Running a Shard

```bash
# Start shard 0
./context-hub shard --shard-id 0 --addr 0.0.0.0:8080

# Start shard 1 on different node
./context-hub shard --shard-id 1 --addr 0.0.0.0:8080

# Start shard 2 on different node
./context-hub shard --shard-id 2 --addr 0.0.0.0:8080
```

### Running the Gateway

```bash
./context-hub gateway --addr 0.0.0.0:80
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: context-hub-shard
spec:
  serviceName: context-hub
  replicas: 3
  selector:
    matchLabels:
      app: context-hub-shard
  template:
    metadata:
      labels:
        app: context-hub-shard
    spec:
      containers:
      - name: shard
        image: context-hub:latest
        command: ["/app/context-hub", "shard"]
        args:
          - "--shard-id"
          - "$(SHARD_ID)"
        env:
        - name: SHARD_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.annotations['shard-id']
        - name: ETCD_ENDPOINTS
          value: "http://etcd:2379"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: context-hub-secrets
              key: database-url
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: wal-storage
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: wal-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 100Gi
```

## API Usage

### Authentication

```bash
# Login
curl -X POST https://api.context-hub.io/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secure-password"}'

# Response
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 900,
  "token_type": "Bearer"
}

# Use access token
curl https://api.context-hub.io/documents \
  -H "Authorization: Bearer eyJ..."
```

### Document Operations

```bash
# Create document
curl -X POST https://api.context-hub.io/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Document",
    "content": "Hello, World!",
    "doc_type": "Text"
  }'

# Update document
curl -X PUT https://api.context-hub.io/documents/$DOC_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated content",
    "version": 1
  }'

# Share document
curl -X POST https://api.context-hub.io/documents/$DOC_ID/share \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "other-user@example.com",
    "access_level": "write"
  }'
```

### Real-time Sync

```javascript
// WebSocket connection for real-time updates
const ws = new WebSocket('wss://api.context-hub.io/documents/123/sync');

ws.on('open', () => {
  ws.send(JSON.stringify({
    type: 'auth',
    token: accessToken
  }));
});

ws.on('message', (data) => {
  const update = JSON.parse(data);
  // Apply CRDT operations to local document
  document.applyOps(update.ops);
});
```

## Performance Characteristics

### Latency
- Cache hit: < 1ms
- Database query: < 10ms  
- Document create: < 50ms (p99)
- Document update: < 30ms (p99)
- Search query: < 100ms (p99)

### Throughput
- 10,000 writes/second per shard
- 100,000 reads/second per shard
- 1M concurrent WebSocket connections

### Scalability
- Horizontal scaling via sharding
- Support for 1000+ shards
- 50,000 users per shard
- 100GB storage per shard

## Monitoring

### Metrics (Prometheus)
- Request rate and latency
- Shard health and capacity
- Cache hit ratio
- WAL lag and size
- Replication lag

### Alerts
- Shard down > 1 minute
- Disk usage > 80%
- Memory usage > 90%
- Replication lag > 5 seconds
- Error rate > 1%

### Dashboards (Grafana)
- Cluster overview
- Shard distribution
- User activity
- Performance metrics
- Error tracking

## Security

### Encryption
- TLS 1.3 for all connections
- AES-256-GCM for data at rest
- Per-user encryption keys
- Encrypted S3 buckets

### Authentication
- JWT with RS256 signing
- Short-lived access tokens (15 min)
- Refresh token rotation
- MFA support (TOTP)

### Authorization
- Document-level ACLs
- Role-based access control
- Agent scope restrictions
- Audit logging

## Disaster Recovery

### Backup Strategy
- Continuous WAL archival to S3
- Daily PostgreSQL backups
- Cross-region replication
- Point-in-time recovery

### Failover Process
1. etcd detects shard failure
2. Replica promoted to primary
3. Traffic rerouted automatically
4. New replica spawned
5. Data resynced from WAL

### Recovery Time
- RTO: < 30 seconds
- RPO: < 1 second

## Development

### Building

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build release binary
cargo build --release --bin context-hub

# Run tests
cargo test

# Run benchmarks
cargo bench
```

### Testing

```bash
# Unit tests
cargo test --lib

# Integration tests
cargo test --test '*'

# Load testing
k6 run scripts/load-test.js
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

Copyright 2024 - All rights reserved