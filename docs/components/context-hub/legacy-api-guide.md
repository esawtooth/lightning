# Lightning Context Hub API Guide

The Lightning Context Hub provides a sophisticated document management system with advanced features designed for both human and AI interaction. This guide covers all available APIs and their usage patterns.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [Core Concepts](#core-concepts)
4. [Document Management](#document-management)
5. [LLM-Friendly Features](#llm-friendly-features)
6. [Search and Discovery](#search-and-discovery)
7. [Folder Organization](#folder-organization)
8. [Index Guides](#index-guides)
9. [Error Handling](#error-handling)
10. [Examples](#examples)

## Quick Start

### Base URL
- Local Development: `http://localhost:3000`
- Docker Network: `http://context-hub:3000`

### Required Headers
All requests must include:
```http
X-User-Id: your-user-id
Content-Type: application/json
```

### Simple Example
```bash
# Create a document
curl -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{"name": "Hello World", "content": "Hello, World!"}' \
  http://localhost:3000/docs

# Get document with line numbers
curl -H "X-User-Id: demo-user" \
  "http://localhost:3000/docs/{document-id}?format=numbered"
```

## Authentication

The Context Hub uses header-based user identification:

```http
X-User-Id: demo-user
```

This header identifies the user context for all operations. Documents are scoped to the user making the request.

## Core Concepts

### Document Types

1. **Text** - Standard text documents
2. **Folder** - Directory containers for organization
3. **IndexGuide** - Special contextual documents that provide guidance

### Hierarchical Organization

Documents can be organized in a folder hierarchy:
- Root level documents have `parent_folder_id: null`
- Nested documents reference their parent folder by UUID
- Folders are special documents with `doc_type: "Folder"`

### Unique Features

- **CRDT Synchronization**: Conflict-free distributed updates
- **Full-text Search**: Integrated search indexing
- **Line-numbered Content**: Precise editing support
- **Patch-based Editing**: Efficient content updates
- **Index Guides**: Contextual document organization

## Document Management

### Creating Documents

Create a standard text document:
```bash
curl -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Document",
    "content": "This is my document content.",
    "doc_type": "Text"
  }' \
  http://localhost:3000/docs
```

Create a folder:
```bash
curl -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Folder",
    "content": "",
    "doc_type": "Folder"
  }' \
  http://localhost:3000/docs
```

Create a document inside a folder:
```bash
curl -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Nested Document",
    "content": "This document is inside a folder.",
    "parent_folder_id": "550e8400-e29b-41d4-a716-446655440000",
    "doc_type": "Text"
  }' \
  http://localhost:3000/docs
```

### Retrieving Documents

Get a document:
```bash
curl -H "X-User-Id: demo-user" \
  http://localhost:3000/docs/{document-id}
```

List all documents:
```bash
curl -H "X-User-Id: demo-user" \
  http://localhost:3000/docs
```

### Updating Documents

Replace entire content:
```bash
curl -X PUT \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{"content": "New content for the document"}' \
  http://localhost:3000/docs/{document-id}
```

### Deleting Documents

```bash
curl -X DELETE \
  -H "X-User-Id: demo-user" \
  http://localhost:3000/docs/{document-id}
```

## LLM-Friendly Features

### Line-Numbered Content Retrieval

For precise editing by LLMs, request line-numbered content:

```bash
curl -H "X-User-Id: demo-user" \
  "http://localhost:3000/docs/{document-id}?format=numbered"
```

Response includes:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Sample Document",
  "content": "Line 1\nLine 2\nLine 3",
  "numbered_content": "1: Line 1\n2: Line 2\n3: Line 3",
  "line_count": 3,
  ...
}
```

### Patch-Based Editing

Apply precise edits using unified diff patches:

```bash
curl -X PATCH \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": "--- a/document\n+++ b/document\n@@ -1,3 +1,3 @@\n Line 1\n-Line 2\n+Modified Line 2\n Line 3"
  }' \
  http://localhost:3000/docs/{document-id}
```

#### Patch Format

Unified diff format with hunk headers:
```diff
--- a/filename
+++ b/filename
@@ -start,count +start,count @@
 context line
-removed line
+added line
 context line
```

#### Benefits for LLMs

1. **Precision**: Edit specific lines without affecting others
2. **Efficiency**: No need to send entire document content
3. **Context**: Clear indication of what changed
4. **Safety**: Patches can be validated before application

### LLM Workflow Example

1. **Get line-numbered content** for precise reference:
   ```bash
   GET /docs/{id}?format=numbered
   ```

2. **Generate patch** based on line numbers:
   ```diff
   @@ -5,3 +5,3 @@
    def calculate():
   -    return 42
   +    return sum([1, 2, 3])
    
   ```

3. **Apply patch** efficiently:
   ```bash
   PATCH /docs/{id}
   {"patch": "..."}
   ```

## Search and Discovery

### Full-Text Search

Search across all documents:
```bash
curl -H "X-User-Id: demo-user" \
  "http://localhost:3000/search?q=machine%20learning&limit=20"
```

Parameters:
- `q`: Search query (required)
- `limit`: Maximum results (default: 10, max: 100)
- `offset`: Skip results for pagination (default: 0)

### Search Results

Returns document summaries with snippets:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "ML Algorithms",
    "snippet": "Machine learning algorithms are powerful tools...",
    "doc_type": "Text",
    "updated_at": "2025-06-20T06:37:19Z",
    "index_guide": "# AI Research Guide\nThis folder contains..."
  }
]
```

## Folder Organization

### Folder Contents

Get all documents in a folder:
```bash
curl -H "X-User-Id: demo-user" \
  http://localhost:3000/folders/{folder-id}
```

### Folder Hierarchy

Organize documents in hierarchies:
```
Root/
├── Projects/
│   ├── AI Research/
│   │   ├── algorithms.md
│   │   └── datasets.md
│   └── Web Development/
│       └── backend.md
└── Notes/
    └── meeting-notes.md
```

## Index Guides

Index Guides provide contextual information about folders and their contents.

### Getting Folder Guides

```bash
curl -H "X-User-Id: demo-user" \
  http://localhost:3000/folders/{folder-id}/guide
```

### How Index Guides Work

1. **Hierarchical Collection**: Guides are collected from root to current folder
2. **Contextual Information**: Each guide provides context for its level
3. **Automatic Integration**: Document responses include relevant guides
4. **Separation**: Multiple guides are separated by `---`

### Example Guide Response

```json
{
  "content": "# Root Project Guide\nThis is the main project directory.\n\n---\n\n# AI Research Guide\nThis folder contains machine learning research documents."
}
```

## Error Handling

### HTTP Status Codes

- `200`: Success
- `201`: Created
- `204`: No Content (successful deletion/update)
- `400`: Bad Request (invalid input)
- `404`: Not Found
- `500`: Internal Server Error

### Error Response Format

```json
{
  "error": "DocumentNotFound",
  "message": "The requested document could not be found",
  "details": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## Examples

### Complete Document Workflow

```bash
# 1. Create a project folder
FOLDER_RESPONSE=$(curl -s -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{"name": "AI Project", "content": "", "doc_type": "Folder"}' \
  http://localhost:3000/docs)

FOLDER_ID=$(echo $FOLDER_RESPONSE | jq -r '.id')

# 2. Create an index guide for the folder
curl -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"INDEX_GUIDE.md\",
    \"content\": \"# AI Project Guide\nThis folder contains AI research documents.\",
    \"parent_folder_id\": \"$FOLDER_ID\",
    \"doc_type\": \"IndexGuide\"
  }" \
  http://localhost:3000/docs

# 3. Create a document in the folder
DOC_RESPONSE=$(curl -s -X POST \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"algorithm.py\",
    \"content\": \"def calculate():\n    return 42\n\nresult = calculate()\",
    \"parent_folder_id\": \"$FOLDER_ID\",
    \"doc_type\": \"Text\"
  }" \
  http://localhost:3000/docs)

DOC_ID=$(echo $DOC_RESPONSE | jq -r '.id')

# 4. Get document with line numbers
curl -H "X-User-Id: demo-user" \
  "http://localhost:3000/docs/$DOC_ID?format=numbered"

# 5. Apply a patch to improve the algorithm
curl -X PATCH \
  -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": "--- a/algorithm.py\n+++ b/algorithm.py\n@@ -1,4 +1,4 @@\n def calculate():\n-    return 42\n+    return sum([1, 2, 3, 4, 5])\n \n result = calculate()"
  }' \
  http://localhost:3000/docs/$DOC_ID

# 6. Search for algorithms
curl -H "X-User-Id: demo-user" \
  "http://localhost:3000/search?q=calculate&limit=5"
```

### LLM Integration Pattern

```python
import requests
import json

class ContextHubClient:
    def __init__(self, base_url="http://localhost:3000", user_id="demo-user"):
        self.base_url = base_url
        self.headers = {
            "X-User-Id": user_id,
            "Content-Type": "application/json"
        }
    
    def get_document_with_lines(self, doc_id):
        """Get document with line numbers for precise editing"""
        response = requests.get(
            f"{self.base_url}/docs/{doc_id}?format=numbered",
            headers=self.headers
        )
        return response.json()
    
    def apply_patch(self, doc_id, patch):
        """Apply a unified diff patch to a document"""
        response = requests.patch(
            f"{self.base_url}/docs/{doc_id}",
            headers=self.headers,
            json={"patch": patch}
        )
        return response.json()
    
    def search_documents(self, query, limit=10):
        """Search documents with full-text search"""
        response = requests.get(
            f"{self.base_url}/search",
            headers=self.headers,
            params={"q": query, "limit": limit}
        )
        return response.json()

# Usage example
client = ContextHubClient()

# Get document for editing
doc = client.get_document_with_lines("your-doc-id")
print(f"Lines: {doc['line_count']}")
print(doc['numbered_content'])

# Apply precise edit
patch = """--- a/file
+++ b/file
@@ -2,3 +2,3 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
"""
result = client.apply_patch("your-doc-id", patch)
```

## Advanced Features

### Batch Operations

For multiple operations, consider using the Lightning API proxy which provides batching capabilities.

### Real-time Updates

The Context Hub supports real-time synchronization through CRDT operations, ensuring consistency across distributed access.

### Performance Optimization

- Use line-numbered format only when needed for editing
- Apply patches instead of full content updates for large documents
- Use search with appropriate limits for discovery
- Leverage folder organization for logical grouping

### Integration with Lightning Core

The Context Hub integrates seamlessly with Lightning's event-driven architecture:
- Document changes trigger events
- Search indexing happens automatically
- CRDT synchronization maintains consistency

For more information, see the [OpenAPI specification](./context-hub/CONTEXT_HUB_API.yaml).