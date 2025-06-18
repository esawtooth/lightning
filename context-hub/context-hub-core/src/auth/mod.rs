#[cfg(feature = "distributed")]
pub mod distributed;
pub mod legacy;

// Re-export legacy types for backward compatibility
pub use legacy::{Claims, TokenVerifier};