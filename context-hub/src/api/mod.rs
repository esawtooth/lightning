//! API modules for Context Hub

#[cfg(feature = "distributed")]
pub mod distributed;

// Legacy single-node API - enabled by default when distributed is not available
#[cfg(not(feature = "distributed"))]
pub mod legacy;

#[cfg(not(feature = "distributed"))]
pub use legacy::router;