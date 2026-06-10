//! M-B′: Spartan CPS.Comm / CPS.Ver — partial wiring via commit_model digest.

use crate::commit::{commit_model, ModelCommitmentBundle};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CpsCommitment {
    pub cm_hex: String,
    pub num_scalars: usize,
}

#[derive(Clone, Debug)]
pub enum CpsError {
    NotImplemented(&'static str),
}

impl std::fmt::Display for CpsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CpsError::NotImplemented(m) => write!(f, "CPS not implemented: {m}"),
        }
    }
}

impl std::error::Error for CpsError {}

/// B′.1: cm_W ← CPS.Comm(W*) — MVP uses Pedersen commit_model until unified CPS.Ver.
pub fn cps_comm_w_star(weights: &[u128]) -> Result<CpsCommitment, CpsError> {
    if weights.is_empty() {
        return Err(CpsError::NotImplemented("empty weights"));
    }
    let (bundle, _, _): (ModelCommitmentBundle, _, _) = commit_model(weights);
    Ok(CpsCommitment {
        cm_hex: bundle.cm_weights.point_hex,
        num_scalars: weights.len(),
    })
}

/// B′.3: unified CPS.Ver(π, (cm_W, cm'), t) — stub until M5 φ closed.
pub fn cps_ver_unified(
    _pi_bytes: &[u8],
    cm_w: &CpsCommitment,
    cm_aux: &CpsCommitment,
) -> Result<bool, CpsError> {
    if cm_w.cm_hex.is_empty() || cm_aux.cm_hex.is_empty() {
        return Ok(false);
    }
    Err(CpsError::NotImplemented("CPS.Ver unified"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cps_comm_w_star_network_a_sample() {
        let w = vec![1u128, 2, 3];
        let c = cps_comm_w_star(&w).unwrap();
        assert_eq!(c.num_scalars, 3);
        assert!(!c.cm_hex.is_empty());
    }
}
