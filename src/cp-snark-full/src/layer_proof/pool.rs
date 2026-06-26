//! Average pooling computational proof (paper: *Proving Average Pooling*).
//!
//! Algorithm:
//! 1. Homomorphic **sum** over k̂×k̂ window (Eq. 7): `JB[i,j] = Σ JA[window]`.
//! 2. Multiply by public fixed-point `1/k̂²` off-circuit (`Server.py` `realNumbersToFixedPointRepresentation`).
//! 3. Prove sum with **PtAdd** chain only (no RLC in paper for pooling).

use super::gadget::{LayerGadgetSchedule, PtAddSlot};
use super::verify::{verify_pool_eq7_per_cell, LayerProofResult};

/// One average-pooling layer (sum stage before public scaling).
#[derive(Clone, Debug)]
pub struct PoolLayerProofSpec {
    pub windows: Vec<Vec<u128>>,
    /// Homomorphic sum per window (before × 1/k̂²).
    pub output_sums: Vec<u128>,
    /// Public fixed-point scalar for `1/k̂²` (e.g. `Server.py` bits=10).
    pub inv_k_squared_fp: u128,
}

impl PoolLayerProofSpec {
    pub fn verify_eq7(&self) -> LayerProofResult<()> {
        verify_pool_eq7_per_cell(self)
    }

    /// PtAdd chain per window (matches `myAvgPool2d` flag=1 recording).
    pub fn build_gadget_schedule(&self) -> LayerGadgetSchedule {
        let mut schedule = LayerGadgetSchedule::default();
        for window in &self.windows {
            if window.len() < 2 {
                continue;
            }
            let mut acc = window[0];
            for &v in window.iter().skip(1) {
                schedule.pt_adds.push(PtAddSlot {
                    augend: acc,
                    addend: v,
                });
                acc = v;
            }
        }
        schedule
    }

    /// After public scaling (witness for optional PtMul slot): sum × inv_k_squared_fp.
    pub fn scaled_output(&self, window_index: usize) -> Option<u128> {
        let sum = self.output_sums.get(window_index)?;
        Some(sum.saturating_mul(self.inv_k_squared_fp))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pool_eq7_toy() {
        let spec = PoolLayerProofSpec {
            windows: vec![vec![2, 3, 4, 5]],
            output_sums: vec![14],
            inv_k_squared_fp: 1,
        };
        spec.verify_eq7().unwrap();
        assert_eq!(spec.build_gadget_schedule().num_pt_adds(), 3);
    }
}
