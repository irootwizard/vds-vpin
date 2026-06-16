//! Client-side SNARK verification (not scalar `statement::check`).

pub mod ec;
pub mod layer;
pub mod mac;
pub mod pipeline;

pub use pipeline::verifier_pipeline;
