# Context Hub - Production Architecture

## Overview

Context Hub is redesigned as a distributed, sharded storage system optimized for collaborative document editing with CRDT support. The system is designed for horizontal scalability, fault tolerance, and production-grade performance.

## Core Design Principles

1. **User-based Sharding**: Documents are sharded by user ID for optimal locality
2. **Append-Only Log**: All mutations go through a durable write-ahead log
3. **Eventual Consistency**: CRDTs provide conflict-free distributed editing
4. **Multi-Layer Storage**: Hot data in memory/cache, warm in DB, cold in object storage
5. **Zero-Trust Security**: End-to-end encryption, fine-grained access control

## Architecture Components

### 1. API Gateway Layer
- **Load Balancer**: Routes requests to appropriate shard
- **Rate Limiter**: Token bucket per user/IP
- **Auth Service**: JWT validation, refresh tokens, API keys
- **Request Router**: Determines shard based on user ID

### 2. Shard Coordination Layer
- **Shard Registry**: Tracks which users map to which shards
- **Rebalancer**: Moves users between shards for load distribution
- **Health Monitor**: Tracks shard health and triggers failover
- **Distributed Lock Manager**: Coordinates cross-shard operations

### 3. Storage Shard (per user group)
Each shard handles a subset of users and consists of:

- **Write-Ahead Log (WAL)**: Append-only log for all mutations
- **CRDT Engine**: Processes and merges concurrent edits
- **Document Cache**: LRU cache of active documents
- **Metadata Store**: PostgreSQL for document metadata, ACLs
- **Blob Storage**: S3-compatible store for large attachments
- **Search Index**: Elasticsearch shard for full-text search

### 4. Synchronization Layer
- **Change Stream**: Publishes document changes for real-time sync
- **WebSocket Gateway**: Manages persistent connections
- **Sync Queue**: Ensures ordered delivery of updates
- **Vector Clocks**: Tracks causality for distributed edits

### 5. Background Services
- **Compaction Service**: Merges WAL segments, compacts CRDTs
- **Snapshot Service**: Creates periodic consistent snapshots
- **Garbage Collector**: Removes deleted documents after retention
- **Audit Logger**: Tracks all access for compliance

## Data Flow

### Write Path
1. Client sends mutation to API Gateway
2. Gateway authenticates and routes to correct shard
3. Shard appends to WAL (durability)
4. CRDT engine processes mutation
5. Update written to cache and metadata store
6. Change published to sync stream
7. Connected clients receive update

### Read Path
1. Check cache (Redis) - sub-ms latency
2. Check metadata store (PostgreSQL) - single-digit ms
3. Reconstruct from WAL if needed - 10s of ms
4. Stream from blob storage for large docs

## Sharding Strategy

### User-Based Sharding
- Shard key: hash(user_id) % num_shards
- Co-locate all user's documents on same shard
- Shared folders replicated across relevant shards

### Shard Sizing
- Target: 10k-50k users per shard
- Monitor: < 70% CPU, < 10GB memory per shard
- Auto-scale: Split shards when thresholds exceeded

## High Availability

### Replication
- 3-way replication per shard (1 primary, 2 replicas)
- Synchronous replication to at least 1 replica
- Automatic failover via Raft consensus

### Backup Strategy
- Continuous WAL archival to S3
- Daily full backups of metadata
- Point-in-time recovery to any second

## Security

### Encryption
- TLS 1.3 for all client connections
- Encryption at rest for all storage
- Optional client-side encryption for sensitive docs

### Access Control
- JWT tokens with short expiry (15 min)
- Refresh tokens stored in secure HTTP-only cookies
- Fine-grained ACLs with inheritance
- Audit log of all access

## Performance Targets

- **Latency**: p99 < 100ms for document operations
- **Throughput**: 10k writes/sec per shard
- **Availability**: 99.99% uptime
- **Durability**: 11 nines via S3 storage
- **Scale**: Support 1M+ concurrent users

## Technology Stack

- **Language**: Rust (performance, memory safety)
- **WAL**: Custom append-only log on NVMe SSDs
- **Cache**: Redis Cluster with persistence
- **Metadata**: PostgreSQL with Citus sharding
- **Blob Storage**: S3-compatible (MinIO/AWS S3)
- **Search**: Elasticsearch cluster
- **Message Queue**: Apache Pulsar for change streams
- **Coordination**: etcd for distributed consensus
- **Monitoring**: Prometheus + Grafana
- **Tracing**: Jaeger for distributed tracing