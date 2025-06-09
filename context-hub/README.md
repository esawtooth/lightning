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
- `POST /docs` – create a new document. Body: `{ "content": "text" }`.
- `GET /docs/:id` – fetch a document by UUID.
- `PUT /docs/:id` – replace document text. Body: `{ "content": "text" }`.
- `DELETE /docs/:id` – remove a document.

Documents are stored as Automerge CRDTs and persisted as binary files under the `data` directory.
