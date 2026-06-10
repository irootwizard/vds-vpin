//! Per-layer computational **statements** (scalar MAC/RLC); SNARK proofs live in `prove/` / `verify/`.
//!
//! See [`README.md`](README.md). Legacy module name: `layer_proof` (re-export alias in `lib.rs`).

pub mod layer_id;
pub mod topology;
pub mod coverage;

pub use crate::layer_proof::{
    common, conv, fc, gadget, pool, rlc, stack, verify,
};

pub use common::{challenge_for_stage, fold_rlc, LayerProofStage, ProofCoverage};
pub use conv::ConvLayerProofSpec;
pub use fc::FcLayerProofSpec;
pub use gadget::{LayerGadgetSchedule, PtAddSlot, PtMulSlot};
pub use pool::PoolLayerProofSpec;
pub use stack::ServerLinearProofStack;
pub use coverage::ProofCoverageV2;
pub use layer_id::{LayerId, LayerKind};
pub use topology::NetworkTopology;

/// Scalar statement checks (not SNARK `verify`).
pub mod check {
    pub use crate::layer_proof::verify::{
        verify_conv_eq5_per_cell, verify_conv_eq9_rlc, verify_fc_eq8_per_output,
        verify_fc_eq10_rlc, verify_pool_eq7_per_cell, LayerProofError, LayerProofResult,
    };
}

pub type StatementError = check::LayerProofError;
pub type StatementResult<T> = check::LayerProofResult<T>;
