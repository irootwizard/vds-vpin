//! Shared metadata for multi-layer computational proofs (no model commitment).

use libspartan::scalar::Scalar;

use crate::challenge::ClientChallenge;

pub use super::rlc::fold_rlc;

/// CNN stage covered by server-side computational proofs in vPIN.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum LayerProofStage {
    Convolution,
    AveragePooling,
    FullyConnected,
}

/// Honest statement of what `protocol.json` proofs actually cover today.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum ProofCoverage {
    /// Only `point_add` / `point_mult` EC gadgets (current default).
    EcGadgetOnly,
    /// + convolution RLC/MAC (paper Eq. 9) scalar + gadget schedule.
    ConvRlc,
    /// + pooling PtAdd chain (Eq. 7).
    PoolAdd,
    /// + FC RLC (paper Eq. 10).
    FcRlc,
    /// Full server-side linear stack per paper Remark.
    ServerLinearLayers,
}

impl ProofCoverage {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::EcGadgetOnly => "ec_gadget_only",
            Self::ConvRlc => "conv_rlc",
            Self::PoolAdd => "pool_add",
            Self::FcRlc => "fc_rlc",
            Self::ServerLinearLayers => "server_linear_layers",
        }
    }
}

/// Map paper challenges to `ClientChallenge` fields.
pub fn challenge_for_stage(stage: LayerProofStage, ch: &ClientChallenge) -> Scalar {
    match stage {
        LayerProofStage::Convolution => ch.gamma_scalar(),
        LayerProofStage::AveragePooling => ch.gamma_add_scalar(),
        LayerProofStage::FullyConnected => ch.gamma_mult_scalar(),
    }
}
