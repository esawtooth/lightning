# Context Hub

This directory contains a minimal Rust implementation of the Context Hub service.

## Running

```
cargo run
```

The server exposes the following endpoints:

- `GET /health` – simple health check returning `OK`.
- `POST /docs` – create a new document. Body: `{ "content": "text" }`.
- `GET /docs/:id` – fetch a document by UUID.
- `PUT /docs/:id` – replace document text. Body: `{ "content": "text" }`.
- `DELETE /docs/:id` – remove a document.

Documents are stored as Automerge CRDTs and persisted as binary files under the `data` directory.
