//! Phase Z: per-layer R1CS circuits, L1 weight binding, and unified
//! CPS.Ver toy E2E.

pub mod bind_l1;
pub mod cps_ver;
pub mod layer;

pub use layer::{
    conv_mac, fc_mac, pool_sum,
    LayerProofKind,
};
