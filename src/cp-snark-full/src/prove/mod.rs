//! Proof generation (π_mac stub, π_ec production).

pub mod ec;
pub mod layer;
pub mod mac;
pub mod pipeline;

pub use pipeline::prover_pipeline;
