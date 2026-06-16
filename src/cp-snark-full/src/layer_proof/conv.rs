//! Convolutional layer computational proof (paper: *Proving Convolutional Layer Computation*).
//!
//! Algorithm (no model commitment):
//! 1. Homomorphic conv: `[[A[i,j]]]_2 = Σ_{i',j'} F[i',j'] · [[C[·]]]_2`  (Eq. 6 / (5)).
//! 2. Flatten outputs â and per-cell windows from `JC_K`.
//! 3. Verifier samples γ; check Eq. (9): `Σ γ^i â[i] = Σ γ^i · MAC(f, window_i)`.
//! 4. Prove EC ops via PtMul / PtAdd gadgets (same schedule as `Server.py` `rLCR` type=0).

use libspartan::scalar::Scalar;

use super::gadget::{LayerGadgetSchedule, PtAddSlot, PtMulSlot};
use super::rlc::{conv_rlc_left, conv_rlc_right, fold_rlc, mac_filter_window};
use super::verify::{verify_conv_eq5_per_cell, verify_conv_eq9_rlc, LayerProofResult};
use crate::challenge::ClientChallenge;

/// One convolution layer instance (scalar witnesses decoded from homomorphic trace).
#[derive(Clone, Debug)]
pub struct ConvLayerProofSpec {
    /// Filter `f` flattened (length k²).
    pub filter_flat: Vec<u128>,
    /// One sliding window per output cell (each length k²).
    pub windows: Vec<Vec<u128>>,
    /// Flattened outputs â (same order as `windows`).
    pub output_flat: Vec<u128>,
}

impl ConvLayerProofSpec {
    /// Build windows + outputs from padded input and filter (plaintext reference layout).
    pub fn from_plaintext_conv(
        padded: &[Vec<u128>],
        filter: &[Vec<u128>],
        stride: usize,
    ) -> Self {
        let fh = filter.len();
        let fw = filter.first().map(|r| r.len()).unwrap_or(0);
        let h = padded.len();
        let w = padded.first().map(|r| r.len()).unwrap_or(0);
        let oh = (h - fh) / stride + 1;
        let ow = (w - fw) / stride + 1;
        let mut windows = Vec::new();
        let mut output_flat = Vec::new();
        for i in 0..oh {
            for j in 0..ow {
                let mut window = Vec::with_capacity(fh * fw);
                for ii in 0..fh {
                    for jj in 0..fw {
                        window.push(padded[i * stride + ii][j * stride + jj]);
                    }
                }
                let filter_flat: Vec<u128> = filter.iter().flatten().copied().collect();
                let mac = mac_filter_window(&filter_flat, &window);
                let mac_u128 = scalar_to_u128(mac);
                windows.push(window);
                output_flat.push(mac_u128);
            }
        }
        Self {
            filter_flat: filter.iter().flatten().copied().collect(),
            windows,
            output_flat,
        }
    }

    pub fn verify_eq5(&self) -> LayerProofResult<()> {
        verify_conv_eq5_per_cell(self)
    }

    pub fn verify_eq9(&self, challenge: &ClientChallenge) -> LayerProofResult<()> {
        verify_conv_eq9_rlc(self, challenge)
    }

    /// RLC folds (diagnostics).
    pub fn rlc_left(&self, gamma: &Scalar) -> Scalar {
        conv_rlc_left(&self.output_flat, gamma)
    }

    pub fn rlc_right(&self, gamma: &Scalar) -> Scalar {
        conv_rlc_right(&self.filter_flat, &self.windows, gamma)
    }

    /// Gadget schedule aligned with `Server.py` `rLCR` type=0:
    /// - PtMul: `filter_rlc` coefficients × per-window bases (here: k² filter RLC + one mult per window).
    /// - PtAdd: chain partial sums per window (k²−1 adds) + chain across windows.
    pub fn build_gadget_schedule(&self) -> LayerGadgetSchedule {
        let mut schedule = LayerGadgetSchedule::default();
        let gamma_placeholder = Scalar::one();
        let filter_rlc = fold_rlc(&self.filter_flat, &gamma_placeholder);
        let f_rlc_u128 = scalar_to_u128(filter_rlc);

        for window in &self.windows {
            if window.is_empty() {
                continue;
            }
            schedule.pt_muls.push(PtMulSlot {
                base_scalar: window[0],
                weight_scalar: f_rlc_u128,
            });
            let mut acc = window[0];
            for idx in 1..window.len() {
                schedule.pt_adds.push(PtAddSlot {
                    augend: acc,
                    addend: window[idx],
                });
                acc = window[idx];
            }
        }
        schedule
    }
}

fn scalar_to_u128(s: Scalar) -> u128 {
    let bytes = s.to_bytes();
    let mut buf = [0u8; 16];
    buf.copy_from_slice(&bytes[..16]);
    u128::from_le_bytes(buf)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::challenge::ClientChallenge;

    #[test]
    fn conv_eq5_and_eq9_toy() {
        let spec = ConvLayerProofSpec {
            filter_flat: vec![1, 2, 3, 4],
            windows: vec![vec![1, 0, 1, 0]],
            output_flat: vec![4],
        };
        spec.verify_eq5().unwrap();
        let ch = ClientChallenge::sample(0, 0);
        spec.verify_eq9(&ch).unwrap();
    }

    #[test]
    fn conv_plaintext_layout_matches_mac() {
        let padded = vec![
            vec![1, 0, 1],
            vec![0, 1, 0],
            vec![1, 0, 1],
        ];
        let filter = vec![vec![1, 0], vec![2, 0]];
        let spec = ConvLayerProofSpec::from_plaintext_conv(&padded, &filter, 1);
        spec.verify_eq5().unwrap();
    }
}
