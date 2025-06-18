//! API modules for Context Hub

pub mod distributed;

// Legacy single-node API (deprecated)
#[cfg(feature = "legacy")]
pub mod legacy;