//! HTTP API layer exposing document CRUD endpoints.

pub mod distributed;

// Keep existing single-node implementation for backwards compatibility
mod legacy;
pub use legacy::*;