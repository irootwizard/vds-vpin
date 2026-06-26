//! Fully connected layer computational proof (paper: *Proving FC Layer*, Eq. 8 and 10).
//!
//! Algorithm:
//! 1. `t[j] = Σ_k W[k,j]·d[k] + b[j]` (Eq. 8).
//! 2. Verifier γ′; Eq. (10): `Σ_j γ′^j t[j] = Σ_k d[k]·(Σ_i γ′^i W[k,i]) + Σ_j γ′^j b[j]`.
//! 3. PtMul / PtAdd gadgets (`Server.py` `rLCR` type=1).

use libspartan::scalar::Scalar;

use super::gadget::{LayerGadgetSchedule, PtAddSlot, PtMulSlot};
use super::rlc::{fc_rlc_left, fc_rlc_right};
use super::verify::{verify_fc_eq8_per_output, verify_fc_eq10_rlc, LayerProofResult};
use crate::challenge::ClientChallenge;

/// FC layer: `weights_in_out[k][j] = W[k,j]`, row-major input dimension.
#[derive(Clone, Debug)]
pub struct FcLayerProofSpec {
    pub weights_in_out: Vec<Vec<u128>>,
    pub bias: Vec<u128>,
    pub inputs: Vec<u128>,
    pub outputs: Vec<u128>,
}

impl FcLayerProofSpec {
    pub fn verify_eq8(&self) -> LayerProofResult<()> {
        verify_fc_eq8_per_output(self)
    }

    pub fn verify_eq10(&self, challenge: &ClientChallenge) -> LayerProofResult<()> {
        verify_fc_eq10_rlc(self, challenge)
    }

    pub fn rlc_left(&self, gamma_prime: &Scalar) -> Scalar {
        fc_rlc_left(&self.outputs, gamma_prime)
    }

    pub fn rlc_right(&self, gamma_prime: &Scalar) -> Scalar {
        fc_rlc_right(
            &self.inputs,
            &self.weights_in_out,
            &self.bias,
            gamma_prime,
        )
    }

    /// Gadget schedule (post–Eq. 10): one PtMul per (d[k], W[k,j]) plus bias PtAdd per column.
    pub fn build_gadget_schedule(&self) -> LayerGadgetSchedule {
        let mut schedule = LayerGadgetSchedule::default();
        let out_dim = self.outputs.len();
        for j in 0..out_dim {
            for (k, row) in self.weights_in_out.iter().enumerate() {
                let w = row.get(j).copied().unwrap_or(0);
                schedule.pt_muls.push(PtMulSlot {
                    base_scalar: self.inputs.get(k).copied().unwrap_or(0),
                    weight_scalar: w,
                });
            }
            if let Some(&b) = self.bias.get(j) {
                schedule.pt_adds.push(PtAddSlot {
                    augend: 0,
                    addend: b,
                });
            }
        }
        schedule
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::challenge::ClientChallenge;

    #[test]
    fn fc_eq8_eq10_toy() {
        let spec = FcLayerProofSpec {
            weights_in_out: vec![vec![2, 1], vec![3, 4]],
            bias: vec![1, 0],
            inputs: vec![10, 20],
            outputs: vec![81, 90],
        };
        spec.verify_eq8().unwrap();
        let ch = ClientChallenge::sample(0, 0);
        spec.verify_eq10(&ch).unwrap();
    }
}
