# Context Hub

A Rust-based persistent storage service with CRDT synchronization, providing distributed document storage with real-time collaboration capabilities.

## Features

- **CRDT-based Storage**: Uses [Loro](https://github.com/loro-dev/loro) for conflict-free replicated data types
- **Hierarchical Organization**: Documents and folders with parent-child relationships
- **Full-text Search**: Powered by Tantivy for fast, indexed search
- **Timeline & Versioning**: Complete version history with document replay capabilities
- **Automatic Snapshots**: Git-based snapshots for durability and recovery
- **Authentication**: Supports JWT (HS256) and Azure AD authentication
- **Real-time Updates**: Event bus for live notifications
- **Compression**: Automatic storage optimization

## Architecture

### Core Components

- **Document Store**: CRDT-based document storage with Loro
- **Search Index**: Tantivy-powered full-text search
- **Snapshot Manager**: Git-based snapshot system
- **Timeline**: Version tracking and document replay
- **Event Bus**: Real-time update notifications
- **Compress Service**: Background storage optimization

### Document Types

- **Text**: Regular text documents
- **Folder**: Hierarchical containers
- **IndexGuide**: Metadata documents for folders

## API Endpoints

### Authentication
All endpoints require authentication via one of:
- `Authorization: Bearer <JWT_TOKEN>` header
- `X-User-Id: <username>` header (legacy, for development)

### Document Operations

#### Create Document
```http
POST /docs
Content-Type: application/json

{
  "name": "document.txt",
  "content": "Document content",
  "parent_folder_id": "uuid", // optional
  "doc_type": "Text" // or "Folder"
}
```

#### Get Document
```http
GET /docs/{id}
GET /docs/{id}?format=numbered  // Returns with line numbers
```

#### Update Document
```http
PUT /docs/{id}
Content-Type: application/json

{
  "content": "Updated content"
}
```

#### Patch Document (Unified Diff)
```http
PATCH /docs/{id}
Content-Type: application/json

{
  "patch": "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old line\n+new line"
}
```

#### Delete Document
```http
DELETE /docs/{id}
```

### Folder Operations

#### List Folder Contents
```http
GET /folders/{id}
```

#### Get Folder Guide
```http
GET /folders/{id}/guide
```

### Search

#### Search Documents
```http
GET /search?q=query&limit=10&offset=0
```

### Timeline Operations

#### Get Timeline Info
```http
GET /timeline/info
```

Response:
```json
{
  "snapshots_available": true,
  "snapshot_dir": "snapshots",
  "message": "Timeline snapshots are being created automatically..."
}
```

#### List Snapshots
```http
GET /timeline/snapshots
```

Response:
```json
{
  "snapshots": [
    {
      "timestamp": "2025-06-29T06:19:52.512038302+00:00",
      "message": "Snapshot at 2025-06-29T06:19:52.512038302+00:00"
    }
  ],
  "total_count": 5
}
```

#### Get Document Versions
```http
GET /timeline/versions/{document_id}
```

Response:
```json
{
  "id": "document-uuid",
  "name": "document.txt",
  "versions": [
    {
      "timestamp": "2025-06-29T06:32:28.211623958+00:00",
      "version": "base64-encoded-version"
    }
  ],
  "current_version": "base64-encoded-version"
}
```

#### Replay Document to Version
```http
POST /timeline/replay/{document_id}
Content-Type: application/json

{
  "version": "base64-encoded-version", // optional
  "timestamp": "ISO-8601-timestamp"   // optional
}
```

Response:
```json
{
  "id": "document-uuid",
  "name": "document.txt",
  "content": "Document content at this version",
  "version": "base64-encoded-version",
  "timestamp": "2025-06-29T06:32:36.255561913+00:00",
  "message": "Document state at requested version"
}
```

### User Management

#### Get Root Folder
```http
GET /root
```

Returns the user's root folder (created automatically if needed).

## Running Context Hub

### Development
```bash
cargo run
```

### Production
```bash
cargo build --release
./target/release/context-hub
```

### Configuration

Environment variables:
- `HOST`: Server host (default: "0.0.0.0")
- `PORT`: Server port (default: "3000")
- `DATA_DIR`: Document storage directory (default: "data")
- `SNAPSHOT_DIR`: Snapshot storage directory (default: "snapshots")
- `INDEX_DIR`: Search index directory (default: "index")
- `BLOB_DIR`: Binary blob storage directory (default: "blobs")
- `JWT_SECRET`: Secret for JWT token verification (default: "secret")
- `AZURE_JWKS_URL`: Azure AD JWKS endpoint for token verification
- `SNAPSHOT_RETENTION`: Number of snapshots to retain (default: 10)
- `COMPRESS_THRESHOLD_PERCENT`: Storage compression threshold (default: 100.0)
- `COMPRESS_CHECK_INTERVAL_SECS`: Compression check interval (default: 60)

## CLI Tool

A Python CLI tool (`contexthub-cli.py`) provides a Git-like interface:

### Installation
```bash
pip install -r requirements-cli.txt
```

### Configuration
```bash
ch config user <username>
ch config server <url>
ch config azure <tenant-id> <client-id>  # For Azure AD auth
```

### Basic Commands
```bash
ch status                    # Show workspace status
ch ls [path]                 # List directory contents
ch cd <path>                 # Change directory
ch pwd                       # Show current directory
ch new <name> [-d]           # Create file or folder
ch cat <file>                # View file contents
ch rm <path>                 # Remove file/folder
ch mv <source> <dest>        # Move/rename
ch search <query>            # Search documents
```

### Advanced Commands
```bash
ch pull <remote> <local>     # Pull folder to local filesystem
ch push <local> <remote>     # Push local changes back
ch diff <path> [local-file]  # Show differences
ch patch <path> -f <file>    # Apply patch
```

### LLM-Optimized Commands
```bash
ch llm read <path>           # Read with structured output
ch llm write <path> <content> # Write with structured response
ch llm find <query>          # Search with JSON output
ch llm inspect <path>        # Get detailed path info
```

## Development

### Building
```bash
cargo build
```

### Testing
```bash
cargo test
```

### Benchmarks
```bash
cargo bench
```

## License

Part of the Lightning OS project.