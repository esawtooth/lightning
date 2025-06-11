# Context Hub

This directory contains a minimal Rust implementation of the Context Hub service.

## Running

```
cargo run
```

All API calls require an `X-User-Id` HTTP header identifying the current user.
An optional `X-Agent-Id` header can be supplied when the request originates from
an agent acting on behalf of the user.

The server exposes the following endpoints:

- `GET /health` – simple health check returning `OK`.
- `POST /docs` – create a new document. Body: `{ "name": "file.txt", "content": "text", "parent_folder_id": null, "doc_type": "text" }`.
- `GET /docs/:id` – fetch a document by UUID.
- `PUT /docs/:id` – replace document text. Body: `{ "content": "text" }`.
- `PUT /docs/:id/move` – move a document or folder to a new parent folder. Body: `{ "new_parent_folder_id": "<uuid>" }`.
- `DELETE /docs/:id` – remove a document.
- `GET /folders/:id/guide` – retrieve the Index Guide for a folder.
- `GET /search?q=term` – search documents using a keyword query. Returns only
  results the caller has permission to read.

Documents are stored as Automerge CRDTs and persisted as binary files under the `data` directory. Each document carries an **owner**. When a document is created, the `X-User-Id` header value is recorded as its owner. Existing files loaded from disk default to the user `user1`. The API responses include this `owner` field.

Each document also stores a **name**, optional **parent folder ID**, and a `doc_type` classifying the document (`folder`, `indexGuide`, or `text`).
Documents and folders maintain an **Access Control List (ACL)** containing zero or more permission entries. Each entry names a user or agent and an access level (`read` or `write`). The ACL defaults empty, meaning only the owner can access the item unless additional principals are added.

Optionally, agents can be restricted to specific folders by creating an
`agent_scopes.json` file in the data directory. The file maps a user and agent
to a list of allowed folder UUIDs:

```json
{
  "user1": {
    "scheduler": ["<folder-uuid>"]
  }
}
```

When a request includes `X-Agent-Id`, the configured scope is checked first. If
the target document lies outside the allowed folders, access is denied even if
the user would normally have permission.
