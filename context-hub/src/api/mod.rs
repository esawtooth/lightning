//! API modules for Context Hub

pub mod auth_middleware;

#[cfg(feature = "distributed")]
pub mod distributed;

// Legacy single-node API - enabled by default when distributed is not available
#[cfg(not(feature = "distributed"))]
pub mod legacy;

#[cfg(not(feature = "distributed"))]
pub use legacy::router;

// pub mod timeline_handlers;
// pub mod timeline_websocket;