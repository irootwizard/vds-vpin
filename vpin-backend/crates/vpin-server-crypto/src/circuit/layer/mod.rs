//! Phase Z M5: per-layer R1CS instances (toy network, paper Eqs. 7 / 9 / 10).
//!
//! Each layer module exposes:
//! - `build_<layer>_toy_witness(...)` producing a [`CircuitWitness`].
//! - `build_<layer>_toy_instance(...)` producing the deterministic R1CS [`Instance`]
//!   used by both prover and verifier (so verify can rebuild it).
//! - `prove_<layer>_toy(...)` and `verify_<layer>_toy(...)` wrapping the
//!   transcript-bound `prove_sub_circuit` / `verify_sub_circuit` flow.

pub mod conv_mac;
pub mod fc_mac;
pub mod pool_sum;

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub enum LayerProofKind {
    ConvToy,
    PoolToy,
    FcToy,
}

impl LayerProofKind {
    pub fn circuit_name(self) -> &'static str {
        match self {
            LayerProofKind::ConvToy => "conv_toy",
            LayerProofKind::PoolToy => "pool_toy",
            LayerProofKind::FcToy => "fc_toy",
        }
    }
}
