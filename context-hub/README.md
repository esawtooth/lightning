# Context Hub

This directory contains a minimal Rust implementation of the Context Hub service.

## Running

```
cargo run
```

The server can be configured through environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | address to bind | `0.0.0.0` |
| `PORT` | port to bind | `3000` |
| `DATA_DIR` | directory for live documents | `data` |
| `SNAPSHOT_DIR` | directory for snapshots | `snapshots` |
| `SNAPSHOT_INTERVAL_SECS` | snapshot period in seconds | `3600` |
| `SNAPSHOT_RETENTION` | number of snapshot tags to keep | *(unset)* |
| `INDEX_DIR` | directory for search index | `index` |
| `BLOB_DIR` | directory for blob storage | `blobs` |
| `JWT_SECRET` | HS256 secret when not using Azure AD | `secret` |
| `AZURE_JWKS_URL` | JWKS endpoint for Azure tokens | *(unset)* |

The data, snapshot, index, and blob directories are created automatically if
they do not already exist.

All API calls require an `X-User-Id` HTTP header identifying the current user.
An optional `X-Agent-Id` header can be supplied when the request originates from
an agent acting on behalf of the user.

Alternatively clients may authenticate with a bearer token using the
`Authorization` header. Tokens are verified with either a shared secret
(`JWT_SECRET`) or against an Azure Entra ID JWKS endpoint specified by
`AZURE_JWKS_URL`. The token must contain a `sub` claim with the user ID and may
include an `agent` claim naming the acting agent.

## API Endpoints

### Core Documents

- `POST /docs` – create a new document or folder. Body:
  `{ "name": "file.txt", "content": "text", "parent_folder_id": null, "doc_type": "Text" }`.
- `GET /docs/{id}` – fetch a document by UUID.
- `PUT /docs/{id}` – replace document text. Body `{ "content": "text" }`.
- `PUT /docs/{id}/rename` – change a document or folder name.
- `PUT /docs/{id}/move` – move an item to a new parent folder. Body `{ "new_parent_folder_id": "<uuid>" }`.
- `DELETE /docs/{id}` – remove a document or folder.
- `GET /docs/{id}/sharing` – list ACL entries for a document or folder.

### Folders

- `GET /folders/{id}` – list the immediate children of a folder.
- `GET /folders/{id}/guide` – retrieve the folder's Index Guide document.
- `POST /folders/{id}/share` – share the folder with another user. Body `{ "user": "name", "rights": "read"|"write" }`.
- `DELETE /folders/{id}/share` – revoke a sharing entry. Body `{ "user": "name" }`.

### Search and Events

- `GET /search?q=term` – keyword search across documents.
- `GET /ws` – subscribe to a server-sent-events stream of changes.
- `GET /ws/docs/{id}` – open a WebSocket for real-time edits to a single document.

### Pointer Upload/Download

- `POST /docs/{id}/content?name=FILE` – attach a binary blob and insert a pointer.
- `GET /docs/{id}/content/{index}` – download an attached blob by index.
- `GET /docs/{id}/resolve_pointer?name=FILE` – resolve a named pointer (e.g. git ref).

### Agent Scopes and Snapshots

- `POST /agents/{agentId}/scopes` – restrict an agent to specific folders.
- `DELETE /agents/{agentId}/scopes` – remove scope restrictions.
- `POST /snapshot` – force an immediate snapshot of all documents.
- `POST /restore` – restore from the latest snapshot.
- `GET /snapshots` – list recent snapshot commit IDs and timestamps.
- `GET /snapshots/{rev}/docs/{id}` – fetch a document at a given snapshot.
- `GET /health` – basic health check.

Documents are stored as Automerge CRDTs and persisted as binary files under the `DATA_DIR` directory. Each document carries an **owner**. When a document is created, the `X-User-Id` header value is recorded as its owner. Existing files loaded from disk default to the user `user1`. The API responses include this `owner` field.

Each document also stores a **name**, optional **parent folder ID**, and a `doc_type` classifying the document (`folder`, `indexGuide`, or `text`).
Documents and folders maintain an **Access Control List (ACL)** containing zero or more permission entries. Each entry names a user or agent and an access level (`read` or `write`). The ACL defaults empty, meaning only the owner can access the item unless additional principals are added.

Permissions are hierarchical: sharing a folder grants the recipient the same rights for all documents inside it. Agents must also satisfy any scope restrictions configured in `agent_scopes.json`.

Each folder includes an *Index Guide* document accessible via `GET /folders/{id}/guide`. The guide explains the folder's purpose and how new documents should be organized. Agents should consult this guide before creating new items.

Optionally, agents can be restricted to specific folders by creating an
`agent_scopes.json` file in the `DATA_DIR` directory. The file maps a user and agent
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

Agent scopes can now be managed via the API:

```
POST /agents/{agentId}/scopes   # body: {"folders": ["<folder-uuid>"]}
DELETE /agents/{agentId}/scopes # remove any scope restrictions
```

You can also list sharing information on a document or folder with:

```
GET /docs/{id}/sharing
```

## Example Workflow

1. Create a folder for your project:

   ```bash
   curl -X POST http://localhost:3000/docs \
        -H "X-User-Id: user1" \
        -H "Content-Type: application/json" \
        -d '{"name":"Project","content":"","parent_folder_id":null,"doc_type":"Folder"}'
   ```

   The response returns the new folder ID.

2. Add a text document inside the folder:

   ```bash
   curl -X POST http://localhost:3000/docs \
        -H "X-User-Id: user1" \
        -H "Content-Type: application/json" \
        -d '{"name":"notes.md","content":"initial notes","parent_folder_id":"<folder-id>","doc_type":"Text"}'
   ```

3. Share the folder with another user:

   ```bash
   curl -X POST http://localhost:3000/folders/<folder-id>/share \
        -H "X-User-Id: user1" \
        -H "Content-Type: application/json" \
        -d '{"user":"user2","rights":"write"}'
   ```

4. Search for content:

   ```bash
   curl -H "X-User-Id: user2" "http://localhost:3000/search?q=notes"
   ```

5. Trigger a snapshot and later restore:

   ```bash
   curl -X POST -H "X-User-Id: user1" http://localhost:3000/snapshot
   curl -X POST -H "X-User-Id: user1" http://localhost:3000/restore
   ```

   List snapshots:

   ```bash
   curl -H "X-User-Id: user1" http://localhost:3000/snapshots
   ```
## Command Line Client

A helper script `contexthub` is available in the repository root. It provides
bash-like commands for working with the service using the `click` library.

```bash
# create a folder
./contexthub user1 new Project --type folder

# list folder contents
./contexthub user1 ls <folder-id>
```

Use `-h` with any command to see available options. The base URL can be set with
`--url` or the `HUB_URL` environment variable (default
`http://localhost:3000`). Optionally provide an agent ID with `--agent-id` or the
`AGENT_ID` variable.

Shell completion scripts are available via:

```bash
contexthub completion --shell bash > /usr/local/etc/bash_completion.d/contexthub
```

