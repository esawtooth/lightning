# Context Hub API Guide

The Context Hub provides a RESTful API for document storage, timeline management, and search functionality.

## Base URL

Local development: `http://localhost:3000`
Production: `https://context-hub.your-domain.com`

## Authentication

Context Hub uses bearer token authentication:
```
Authorization: Bearer <token>
```

## Document Operations

### Create Document
```http
POST /documents
Content-Type: application/json

{
  "id": "doc-123",
  "content": {
    "title": "My Document",
    "body": "Document content"
  },
  "metadata": {
    "tags": ["important", "draft"],
    "author": "user@example.com"
  }
}
```

### Get Document
```http
GET /documents/doc-123
```

Response:
```json
{
  "id": "doc-123",
  "content": {
    "title": "My Document", 
    "body": "Document content"
  },
  "metadata": {
    "tags": ["important", "draft"],
    "author": "user@example.com",
    "created_at": "2023-01-01T00:00:00Z",
    "updated_at": "2023-01-01T00:00:00Z",
    "version": 1
  }
}
```

### Update Document
```http
PUT /documents/doc-123
Content-Type: application/json

{
  "content": {
    "title": "Updated Document",
    "body": "Updated content"
  }
}
```

### Delete Document
```http
DELETE /documents/doc-123
```

### List Documents
```http
GET /documents?limit=10&offset=0&tags=important
```

## Timeline Operations

### Get Timeline
```http
GET /timeline?start=2023-01-01T00:00:00Z&end=2023-01-02T00:00:00Z&limit=100
```

Response:
```json
{
  "events": [
    {
      "id": "event-123",
      "timestamp": "2023-01-01T12:00:00Z",
      "event_type": "document.created",
      "document_id": "doc-123",
      "data": {
        "title": "My Document"
      }
    }
  ],
  "total": 1,
  "has_more": false
}
```

### Scrub Timeline
```http
POST /timeline/scrub
Content-Type: application/json

{
  "timestamp": "2023-01-01T12:00:00Z"
}
```

### Replay Events
```http
POST /timeline/replay
Content-Type: application/json

{
  "from": "2023-01-01T00:00:00Z",
  "to": "2023-01-01T12:00:00Z",
  "event_types": ["document.created", "document.updated"]
}
```

## Search Operations

### Search Documents
```http
GET /search?q=document+content&limit=10&offset=0
```

Response:
```json
{
  "results": [
    {
      "id": "doc-123",
      "score": 0.95,
      "highlights": {
        "title": ["My <em>Document</em>"],
        "body": ["Document <em>content</em>"]
      },
      "document": {
        "id": "doc-123",
        "content": {
          "title": "My Document",
          "body": "Document content"
        }
      }
    }
  ],
  "total": 1,
  "took_ms": 5
}
```

### Rebuild Search Index
```http
POST /index/rebuild
```

## Snapshot Operations

### Create Snapshot
```http
POST /snapshots
Content-Type: application/json

{
  "name": "backup-2023-01-01",
  "description": "Daily backup"
}
```

### List Snapshots
```http
GET /snapshots
```

Response:
```json
{
  "snapshots": [
    {
      "id": "snapshot-123",
      "name": "backup-2023-01-01", 
      "description": "Daily backup",
      "created_at": "2023-01-01T00:00:00Z",
      "size_bytes": 1024000,
      "document_count": 100
    }
  ]
}
```

### Restore Snapshot
```http
POST /snapshots/snapshot-123/restore
```

## WebSocket API

### Timeline Events
```javascript
const ws = new WebSocket('ws://localhost:3000/timeline/events');

ws.onmessage = (event) => {
  const timelineEvent = JSON.parse(event.data);
  console.log('Timeline event:', timelineEvent);
};
```

### Search Events
```javascript
const ws = new WebSocket('ws://localhost:3000/search/events');

ws.onmessage = (event) => {
  const searchEvent = JSON.parse(event.data);
  console.log('Search event:', searchEvent);
};
```

## Error Responses

All errors follow a consistent format:
```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with id 'doc-123' not found",
    "details": {
      "document_id": "doc-123"
    }
  }
}
```

## Rate Limiting

API requests are rate limited:
- 1000 requests per minute per IP
- 100 concurrent connections per IP
- Bulk operations have lower limits

## Pagination

List endpoints support pagination:
```http
GET /documents?limit=50&offset=100
```

Response includes pagination metadata:
```json
{
  "data": [...],
  "pagination": {
    "limit": 50,
    "offset": 100,
    "total": 1000,
    "has_more": true
  }
}
```