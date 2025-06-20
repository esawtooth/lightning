# Index Guide Feature Documentation

## Overview

The Index Guide feature provides automatic aggregation of folder-specific instructions and guidelines throughout the Context Hub hierarchy. When accessing documents or folders, the system recursively collects all Index Guides from the root folder down to the current location, providing context-aware guidance to both users and AI agents.

## How It Works

### Index Guide Collection

1. **Recursive Collection**: When a document is accessed, the system walks up the folder hierarchy from the document's location to the root, collecting all Index Guides along the way.

2. **Aggregation**: Index Guides are concatenated in root-to-leaf order, separated by horizontal rules (`---`), ensuring that more general guidelines appear before more specific ones.

3. **Automatic Inclusion**: The aggregated Index Guide content is automatically included in API responses for:
   - Individual document retrieval (`GET /docs/{id}`)
   - Folder content listing (`GET /folders/{id}`)
   - Search results (`GET /search`)
   - Document creation responses (`POST /docs`)

### API Response Structure

All document-related API responses now include an optional `index_guide` field:

```json
{
  "id": "document-uuid",
  "name": "Document Name",
  "content": "Document content...",
  "index_guide": "Aggregated index guide content...",
  // ... other fields
}
```

For search results and folder listings, the `DocumentSummary` structure also includes the `index_guide` field:

```json
{
  "id": "document-uuid",
  "name": "Document Name",
  "snippet": "Content preview...",
  "doc_type": "Text",
  "updated_at": "2024-01-20T12:00:00Z",
  "index_guide": "Aggregated index guide content..."
}
```

### Dedicated Endpoint

A dedicated endpoint is available to retrieve just the aggregated Index Guide for a specific folder:

```
GET /folders/{folder_id}/guide
```

Response:
```json
{
  "content": "Aggregated index guide content..."
}
```

## Integration with ChatAgentDriver

The ChatAgentDriver has been enhanced to leverage Index Guides in several ways:

### 1. System Prompt Enhancement

The system prompt now explicitly mentions Index Guides:

```
IMPORTANT: The context hub may contain "Index Guides" that provide specific instructions on how to use and organize content within folders. Always respect and follow these guides when working with documents. The guides are automatically included with search results and document listings.
```

### 2. Function Response Enhancement

When the AI agent uses context hub functions, Index Guides are prominently displayed:

- **Search Results**: Index Guides are shown before the search results
- **Document Reading**: Index Guides are shown before the document content
- **Folder Listing**: Index Guides are shown before the folder contents

### 3. Example Function Response Format

```
**Folder Guidelines:**
# Root Workspace Guide
This is the root workspace. All documents should be organized into appropriate subfolders.

---

# Projects Folder Guide
This folder contains project-related documents. Each project should have its own subfolder.

---

**Search Results:**
**Project Plan** (ID: abc-123)
This is a sample project plan document...
```

## Creating Index Guides

To create an Index Guide for a folder:

1. Create a document with the name "Index Guide"
2. Set the document type to "IndexGuide"
3. Place it in the target folder
4. The content should provide guidance on:
   - The purpose of the folder
   - How to organize content within it
   - Any naming conventions
   - Special instructions for AI agents

Example Index Guide content:

```markdown
# Research Folder Guide

This folder contains research materials and references for ongoing projects.

## Organization Guidelines
- Create subfolders for each research topic
- Use descriptive file names that include dates
- Include source attribution in document metadata

## AI Assistant Instructions
- When adding new research, always include source citations
- Summarize key findings at the beginning of documents
- Tag documents with relevant keywords for easier search
```

## Benefits

1. **Context Awareness**: AI agents automatically understand folder organization and purpose
2. **Consistency**: Ensures documents are created and organized according to established patterns
3. **User Guidance**: Helps users understand the structure and purpose of different areas
4. **Extensibility**: New folders can have their own guides without modifying code
5. **Hierarchical Instructions**: General guidelines at root level, specific instructions in subfolders

## Testing

Two test scripts are provided:

1. **Rust API Test** (`test_index_guides.py`): Tests the API endpoints directly
2. **ChatAgent Test** (`test_chat_with_index_guides.py`): Tests the AI agent's usage of Index Guides

Run these tests to verify the feature is working correctly:

```bash
# Test the API
cd context-hub
python test_index_guides.py

# Test the ChatAgent integration
cd ../core
python test_chat_with_index_guides.py
```

## Implementation Details

### Rust Side (context-hub)

- `collect_index_guides()` function in `legacy.rs` handles the recursive collection
- All API handlers updated to include Index Guide content
- New `/folders/{id}/guide` endpoint for direct guide retrieval

### Python Side (lightning-core)

- ChatAgentDriver updated to display Index Guides in function responses
- System prompt enhanced to mention Index Guides
- All context hub functions updated to handle the new field

## Future Enhancements

1. **Guide Templates**: Predefined templates for common folder types
2. **Guide Validation**: Ensure guides follow a consistent format
3. **Guide Inheritance**: Allow guides to explicitly inherit from parent guides
4. **Guide Versioning**: Track changes to guides over time
5. **Multi-language Support**: Support guides in different languages