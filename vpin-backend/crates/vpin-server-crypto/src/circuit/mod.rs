//! Phase Z: per-layer R1CS circuits and L1 weight binding.

pub mod bind_l1;
pub mod layer;

pub use layer::{
    conv_mac, fc_mac, pool_sum,
    LayerProofKind,
};
