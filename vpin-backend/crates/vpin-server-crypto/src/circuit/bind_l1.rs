//! Z.4: L1 model-weight binding for the toy network.
//!
//! Connects the full weight vector `W*` (committed via `cm_W`) to the
//! per-layer `vars_para` slots used inside `conv_toy` / `fc_toy` R1CS.
//!
//! Toy `W*` layout (length 13):
//! - `W*[0..9]` → conv filter (used in `conv_toy::vars_para[0..9]`)
//! - `W*[9..11]` → fc weights[0..2] (`fc_toy::vars_para[0..2]`)
//! - `W*[11..13]` → fc bias[0..2] (`fc_toy::vars_para[2..4]`)

use libspartan::scalar::Scalar;

use crate::challenge::ClientChallenge;
use crate::circuit::layer::conv_mac::{prove_conv_toy, ConvToyTrace};
use crate::circuit::layer::fc_mac::{prove_fc_toy, FcToyTrace};
use crate::circuit::layer::pool_sum::{prove_pool_toy, PoolToyTrace};
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::curve::embed_u128_to_scalar;
use crate::protocol::artifacts::SubCircuitProof;

pub const TOY_W_STAR_LEN: usize = 13;

/// Compile-time L1 binding map for the toy network.
#[derive(Clone, Copy, Debug)]
pub struct ToyWeightLayout;

impl ToyWeightLayout {
    pub const CONV_FILTER_RANGE: std::ops::Range<usize> = 0..9;
    pub const FC_WEIGHTS_RANGE: std::ops::Range<usize> = 9..11;
    pub const FC_BIAS_RANGE: std::ops::Range<usize> = 11..13;

    pub fn conv_filter<'a>(w_star: &'a [u128]) -> &'a [u128] {
        &w_star[Self::CONV_FILTER_RANGE]
    }

    pub fn fc_weights<'a>(w_star: &'a [u128]) -> &'a [u128] {
        &w_star[Self::FC_WEIGHTS_RANGE]
    }

    pub fn fc_bias<'a>(w_star: &'a [u128]) -> &'a [u128] {
        &w_star[Self::FC_BIAS_RANGE]
    }
}

/// Returns `Err` if any layer trace uses a value that does not match the
/// corresponding `W*` slot.
pub fn check_l1_binding(
    w_star: &[u128],
    conv: &ConvToyTrace,
    fc: &FcToyTrace,
) -> Result<(), String> {
    if w_star.len() != TOY_W_STAR_LEN {
        return Err(format!(
            "bind_l1: W* len {} != {TOY_W_STAR_LEN}",
            w_star.len()
        ));
    }

    let expected_filter = ToyWeightLayout::conv_filter(w_star);
    if conv.filter != expected_filter {
        return Err(format!(
            "bind_l1: conv filter does not match W*[0..9]: trace={:?} w_star={:?}",
            conv.filter, expected_filter
        ));
    }

    let expected_fc_w = ToyWeightLayout::fc_weights(w_star);
    if fc.weights != expected_fc_w {
        return Err(format!(
            "bind_l1: fc weights mismatch W*[9..11]: trace={:?} w_star={:?}",
            fc.weights, expected_fc_w
        ));
    }

    let expected_fc_b = ToyWeightLayout::fc_bias(w_star);
    if fc.bias != expected_fc_b {
        return Err(format!(
            "bind_l1: fc bias mismatch W*[11..13]: trace={:?} w_star={:?}",
            fc.bias, expected_fc_b
        ));
    }

    Ok(())
}

/// Returns whether the supplied scalar matches the canonical `u128` embedding
/// expected by the L1 binding. Used by audits / Merkle openings (Z.10).
pub fn embed_matches(weight: u128, scalar: &Scalar) -> bool {
    embed_u128_to_scalar(weight) == *scalar
}

/// Bundle of toy layer proofs produced by [`prove_toy_with_binding`].
#[derive(Clone, Debug)]
pub struct ToyLayerProofBundle {
    pub pi_conv: SubCircuitProof,
    pub pi_pool: SubCircuitProof,
    pub pi_fc: SubCircuitProof,
    pub prove_ms_conv: u128,
    pub prove_ms_pool: u128,
    pub prove_ms_fc: u128,
}

/// Prove all three toy layers under a single `W*` (L1 binding enforced).
///
/// Fails with `Err` if the traces do not use `W*[layout]` (this is what makes
/// "tampered W*" prove fail per Phase Z plan Z.4).
pub fn prove_toy_with_binding(
    w_star: &[u128],
    conv: &ConvToyTrace,
    pool: &PoolToyTrace,
    fc: &FcToyTrace,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<ToyLayerProofBundle, String> {
    check_l1_binding(w_star, conv, fc)?;

    let (pi_conv, prove_ms_conv) = prove_conv_toy(conv, model, input, challenge)?;
    let (pi_pool, prove_ms_pool) = prove_pool_toy(pool, model, input, challenge)?;
    let (pi_fc, prove_ms_fc) = prove_fc_toy(fc, model, input, challenge)?;

    Ok(ToyLayerProofBundle {
        pi_conv,
        pi_pool,
        pi_fc,
        prove_ms_conv,
        prove_ms_pool,
        prove_ms_fc,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn w_star() -> Vec<u128> {
        vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7]
    }

    fn conv_trace() -> ConvToyTrace {
        ConvToyTrace {
            filter: vec![1, 0, 1, 2, 0, 2, 1, 0, 1],
            windows: vec![
                vec![1, 2, 3, 5, 6, 7, 9, 10, 11],
                vec![2, 3, 4, 6, 7, 8, 10, 11, 12],
                vec![5, 6, 7, 9, 10, 11, 13, 14, 15],
                vec![6, 7, 8, 10, 11, 12, 14, 15, 16],
            ],
            outputs: vec![48, 56, 80, 88],
        }
    }

    fn fc_trace() -> FcToyTrace {
        FcToyTrace {
            input: 272,
            weights: vec![2, 3],
            bias: vec![5, 7],
            outputs: vec![549, 823],
        }
    }

    #[test]
    fn binding_matches_for_honest_w_star() {
        let w = w_star();
        check_l1_binding(&w, &conv_trace(), &fc_trace()).expect("honest binding");
    }

    #[test]
    fn binding_rejects_tampered_conv_filter() {
        let mut w = w_star();
        w[3] = 99;
        let err = check_l1_binding(&w, &conv_trace(), &fc_trace()).expect_err("should fail");
        assert!(err.contains("conv filter"), "got {err}");
    }

    #[test]
    fn binding_rejects_tampered_fc_weight() {
        let mut w = w_star();
        w[9] = 99;
        let err = check_l1_binding(&w, &conv_trace(), &fc_trace()).expect_err("should fail");
        assert!(err.contains("fc weights"), "got {err}");
    }

    #[test]
    fn binding_rejects_tampered_fc_bias() {
        let mut w = w_star();
        w[12] = 99;
        let err = check_l1_binding(&w, &conv_trace(), &fc_trace()).expect_err("should fail");
        assert!(err.contains("fc bias"), "got {err}");
    }

    #[test]
    fn binding_rejects_wrong_length() {
        let w = vec![1u128; 12];
        let err = check_l1_binding(&w, &conv_trace(), &fc_trace()).expect_err("should fail");
        assert!(err.contains("W* len"), "got {err}");
    }
}
