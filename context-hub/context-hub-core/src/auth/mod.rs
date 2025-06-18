// pub mod distributed; // Requires sqlx
pub mod legacy;

// Re-export legacy types for backward compatibility
pub use legacy::{Claims, TokenVerifier};