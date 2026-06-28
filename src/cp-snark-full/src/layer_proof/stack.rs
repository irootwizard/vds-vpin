//! Ordered server-side linear layers (conv → pool → FC) without activation SNARK.

use super::conv::ConvLayerProofSpec;
use super::fc::FcLayerProofSpec;
use super::pool::PoolLayerProofSpec;
use super::verify::{
    verify_conv_eq9_rlc_only, verify_fc_eq10_rlc_only, verify_pool_eq7_per_cell, LayerProofResult,
};
use crate::challenge::ClientChallenge;

/// Server-side linear stack per vPIN Remark (TReLU is client-side, not included).
#[derive(Clone, Debug, Default)]
pub struct ServerLinearProofStack {
    pub conv: Option<ConvLayerProofSpec>,
    pub pool: Option<PoolLayerProofSpec>,
    pub fc_layers: Vec<FcLayerProofSpec>,
}

impl ServerLinearProofStack {
    /// Scalar MAC/RLC checks (prover-side; not SNARK verify). Alias: `check_all_scalar`.
    pub fn check_all_scalar(&self, challenge: &ClientChallenge) -> LayerProofResult<()> {
        self.verify_all_client(challenge)
    }

    /// Client M1 path: Eq. (9)/(7)/(10) RLC/per-cell only (no Eq. 5 / Eq. 8 per-cell).
    pub fn verify_all_client(&self, challenge: &ClientChallenge) -> LayerProofResult<()> {
        if let Some(conv) = &self.conv {
            verify_conv_eq9_rlc_only(conv, challenge)?;
        }
        if let Some(pool) = &self.pool {
            verify_pool_eq7_per_cell(pool)?;
        }
        for fc in &self.fc_layers {
            verify_fc_eq10_rlc_only(fc, challenge)?;
        }
        Ok(())
    }

    /// Verify all present layers using paper equations (no `cm_W`).
    pub fn verify_all(&self, challenge: &ClientChallenge) -> LayerProofResult<()> {
        if let Some(conv) = &self.conv {
            verify_conv_eq9_rlc_only(conv, challenge)?;
        }
        if let Some(pool) = &self.pool {
            verify_pool_eq7_per_cell(pool)?;
        }
        for fc in &self.fc_layers {
            verify_fc_eq10_rlc_only(fc, challenge)?;
        }
        Ok(())
    }
}
