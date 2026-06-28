//! Honest disclosure of what proofs cover (re-exported from legacy `layer_proof::common`).

pub use crate::layer_proof::ProofCoverage;

/// v2 coverage labels (architecture draft §4.2).
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProofCoverageV2 {
    EcOnly,
    EcPlusL1Binding,
    EcPlusScalarCheck,
    EcPlusMacRlc,
    LayerProofsPlusCps,
}

impl ProofCoverageV2 {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::EcOnly => "ec_only",
            Self::EcPlusL1Binding => "ec_plus_l1_binding",
            Self::EcPlusScalarCheck => "ec_plus_scalar_check",
            Self::EcPlusMacRlc => "ec_plus_mac_rlc",
            Self::LayerProofsPlusCps => "layer_proofs_plus_cps",
        }
    }
}

impl From<ProofCoverage> for ProofCoverageV2 {
    fn from(c: ProofCoverage) -> Self {
        match c {
            ProofCoverage::EcGadgetOnly => Self::EcOnly,
            ProofCoverage::ConvRlc | ProofCoverage::PoolAdd | ProofCoverage::FcRlc => {
                Self::EcPlusScalarCheck
            }
            ProofCoverage::ServerLinearLayers => Self::EcPlusMacRlc,
        }
    }
}
