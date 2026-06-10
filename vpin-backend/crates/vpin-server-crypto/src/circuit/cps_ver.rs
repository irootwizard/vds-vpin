//! Phase Z.6: toy CPS.Ver end-to-end.
//!
//! Wires together the Spartan PC `cm_W` ([`crate::commit::cps`]) with the
//! per-layer toy R1CS SNARK proofs ([`crate::circuit::layer`]) and the L1
//! weight binding ([`crate::circuit::bind_l1`]) into a single bundle a
//! client can present to a verifier.
//!
//! ## Honesty boundary
//!
//! The per-layer SNARK transcripts continue to bind a **Pedersen** model
//! commitment over the full W* (`commit_model(w_star)`) — this is the
//! transcript layer Spartan SNARK encodes (`circuit_prove.rs`). We add a
//! second, canonical Spartan PC `cm_W` on top so the client can persist a
//! single deterministic handle; both commitments must agree on the W*
//! opening, otherwise verification fails (`verify_toy_cps_bundle`).
//!
//! A future milestone (Z.8) is expected to fold `cm_W` into the per-layer
//! transcript and retire the Pedersen variant.

use std::time::Instant;

use serde::{Deserialize, Serialize};

use crate::challenge::ClientChallenge;
use crate::circuit::bind_l1::{
    check_l1_binding, prove_toy_with_binding, ToyLayerProofBundle, ToyWeightLayout, TOY_W_STAR_LEN,
};
use crate::circuit::layer::conv_mac::{verify_conv_toy, ConvToyTrace};
use crate::circuit::layer::fc_mac::{verify_fc_toy, FcToyTrace};
use crate::circuit::layer::pool_sum::{verify_pool_toy, PoolToyTrace};
use crate::commit::cps::{cps_comm_w_star, CpsCommitment};
use crate::commit::{
    commit_model, commit_public_inputs, InputCommitmentBundle, ModelCommitmentBundle,
};
use crate::curve::embed_u128_to_scalar;
use crate::protocol::artifacts::SubCircuitProof;

/// Toy E2E CPS proof bundle: everything a verifier needs to check that a
/// session used the committed model and the client-sampled `γ`.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ToyCpsBundle {
    /// Canonical Spartan PC of W* (Phase Z.5).
    pub cm_w: CpsCommitment,
    /// Plain-text opening of W* (toy: 13 scalars). Production wraps this
    /// in a NIZK opening; for the toy demo we ship it directly.
    pub w_star_opening: Vec<u128>,
    /// Legacy Pedersen commitment over the *same* W*. Still required
    /// because per-layer SNARK transcripts append its `point_hex` /
    /// `digest_hex`. The verifier compares its digest to a recomputed
    /// Pedersen over `w_star_opening` to bind cm_W and cm_model_full.
    pub model_commitment: ModelCommitmentBundle,
    /// Public-input commitment used in per-layer transcripts (toy: derived
    /// from the conv windows).
    pub input_commitment: InputCommitmentBundle,
    /// Client-sampled challenge (γ, γ_add, γ_mult, counts).
    pub challenge: ClientChallenge,
    pub pi_conv: SubCircuitProof,
    pub pi_pool: SubCircuitProof,
    pub pi_fc: SubCircuitProof,
}

#[derive(Clone, Debug)]
pub enum CpsVerError {
    /// `cm_W` recomputed from `w_star_opening` differs from the bundle's
    /// `cm_w` — the opening does not open the published commitment.
    CmWMismatch(String),
    /// W* opening length does not match the toy layout.
    WStarLength(String),
    /// Pedersen `model_commitment.digest_hex` does not match a fresh
    /// `commit_model(w_star_opening)` digest.
    PedersenDigestMismatch(String),
    /// L1 binding rejected (conv/fc/bias slots differ from W* slots).
    L1Binding(String),
    /// A per-layer SNARK rejected.
    LayerVerify(String),
}

impl std::fmt::Display for CpsVerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CpsVerError::CmWMismatch(s) => write!(f, "cm_W mismatch: {s}"),
            CpsVerError::WStarLength(s) => write!(f, "W* length: {s}"),
            CpsVerError::PedersenDigestMismatch(s) => write!(f, "Pedersen digest mismatch: {s}"),
            CpsVerError::L1Binding(s) => write!(f, "L1 binding: {s}"),
            CpsVerError::LayerVerify(s) => write!(f, "layer verify: {s}"),
        }
    }
}

impl std::error::Error for CpsVerError {}

/// Toy traces (conv, pool, fc) required for L1 binding cross-checks.
/// Production protocols transmit these as part of the bundle if the
/// verifier needs them; here we accept them on the side for the toy E2E.
#[derive(Clone, Debug)]
pub struct ToyCpsTraces {
    pub conv: ConvToyTrace,
    pub pool: PoolToyTrace,
    pub fc: FcToyTrace,
}

/// Build the toy bundle: compute cm_W, Pedersen cm_model_full, derive
/// per-layer public-input commitment, then call `prove_toy_with_binding`.
///
/// Returns `Err` if the traces do not match W* (e.g. tampered W*).
pub fn prove_toy_cps(
    w_star: &[u128],
    traces: &ToyCpsTraces,
    challenge: &ClientChallenge,
) -> Result<(ToyCpsBundle, ProveTiming), String> {
    if w_star.len() != TOY_W_STAR_LEN {
        return Err(format!(
            "prove_toy_cps: W* len {} != {TOY_W_STAR_LEN}",
            w_star.len()
        ));
    }
    check_l1_binding(w_star, &traces.conv, &traces.fc)?;

    let t_cm_w = Instant::now();
    let cm_w = cps_comm_w_star(w_star)
        .map_err(|e| format!("cps_comm_w_star: {e}"))?;
    let cm_w_ms = t_cm_w.elapsed().as_millis();

    let (model_commitment, _, _) = commit_model(w_star);

    let public_scalars: Vec<_> = traces
        .conv
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input_commitment, _) = commit_public_inputs(&public_scalars);

    let t_layers = Instant::now();
    let layers: ToyLayerProofBundle = prove_toy_with_binding(
        w_star,
        &traces.conv,
        &traces.pool,
        &traces.fc,
        &model_commitment,
        &input_commitment,
        challenge,
    )?;
    let prove_layers_ms = t_layers.elapsed().as_millis();

    let bundle = ToyCpsBundle {
        cm_w,
        w_star_opening: w_star.to_vec(),
        model_commitment,
        input_commitment,
        challenge: challenge.clone(),
        pi_conv: layers.pi_conv,
        pi_pool: layers.pi_pool,
        pi_fc: layers.pi_fc,
    };
    let timing = ProveTiming {
        cm_w_ms,
        prove_layers_ms,
        prove_ms_conv: layers.prove_ms_conv,
        prove_ms_pool: layers.prove_ms_pool,
        prove_ms_fc: layers.prove_ms_fc,
    };
    Ok((bundle, timing))
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct ProveTiming {
    pub cm_w_ms: u128,
    pub prove_layers_ms: u128,
    pub prove_ms_conv: u128,
    pub prove_ms_pool: u128,
    pub prove_ms_fc: u128,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct VerifyTiming {
    pub cm_w_ms: u128,
    pub verify_layers_ms: u128,
    pub total_ms: u128,
}

/// Verify a toy CPS bundle end-to-end.
///
/// Steps:
/// 1. Length check on `w_star_opening`.
/// 2. Recompute `cm_W` from opening; assert byte-equality with
///    `bundle.cm_w`.
/// 3. Recompute Pedersen `digest_hex` from opening; assert digest equals
///    `bundle.model_commitment.cm_weights.digest_hex` (binds cm_model_full
///    to the same W*). NOTE: this does **not** verify the Pedersen group
///    element (Z.4-style audit would also recompute `point_hex`); the
///    layer SNARK transcript binds the point_hex by reference inside each
///    `verify_X_toy` call below.
/// 4. L1 binding check (uses optional `traces` if available; layer SNARKs
///    already enforce per-circuit R1CS satisfiability).
/// 5. Verify each layer SubCircuitProof.
pub fn verify_toy_cps_bundle(
    bundle: &ToyCpsBundle,
    traces: Option<&ToyCpsTraces>,
) -> Result<VerifyTiming, CpsVerError> {
    let t0 = Instant::now();

    if bundle.w_star_opening.len() != TOY_W_STAR_LEN {
        return Err(CpsVerError::WStarLength(format!(
            "opening len {} != {TOY_W_STAR_LEN}",
            bundle.w_star_opening.len()
        )));
    }

    let t_cm = Instant::now();
    let recomputed = cps_comm_w_star(&bundle.w_star_opening)
        .map_err(|e| CpsVerError::CmWMismatch(format!("recompute cps_comm_w_star: {e}")))?;
    if recomputed != bundle.cm_w {
        return Err(CpsVerError::CmWMismatch(format!(
            "recomputed cm_hex={} != bundle cm_hex={}",
            recomputed.cm_hex, bundle.cm_w.cm_hex
        )));
    }
    let cm_w_ms = t_cm.elapsed().as_millis();

    let (fresh_pedersen, _, _) = commit_model(&bundle.w_star_opening);
    if fresh_pedersen.cm_weights.digest_hex != bundle.model_commitment.cm_weights.digest_hex
        || fresh_pedersen.num_weights != bundle.model_commitment.num_weights
    {
        return Err(CpsVerError::PedersenDigestMismatch(format!(
            "fresh_digest={} bundle_digest={} fresh_num={} bundle_num={}",
            fresh_pedersen.cm_weights.digest_hex,
            bundle.model_commitment.cm_weights.digest_hex,
            fresh_pedersen.num_weights,
            bundle.model_commitment.num_weights,
        )));
    }

    if let Some(t) = traces {
        // Cross-check that supplied traces are consistent with the opening.
        // Verifier-side guard against malformed bundles. Layer SNARKs
        // already enforce R1CS satisfiability.
        check_l1_binding(&bundle.w_star_opening, &t.conv, &t.fc)
            .map_err(CpsVerError::L1Binding)?;
        if !w_star_matches_layer_layout(&bundle.w_star_opening, t) {
            return Err(CpsVerError::L1Binding(
                "trace values not consistent with W* layout".to_string(),
            ));
        }
    }

    let t_layers = Instant::now();
    verify_conv_toy(
        &bundle.pi_conv,
        &bundle.model_commitment,
        &bundle.input_commitment,
        &bundle.challenge,
    )
    .map_err(|e| CpsVerError::LayerVerify(format!("conv: {e}")))?;
    verify_pool_toy(
        &bundle.pi_pool,
        &bundle.model_commitment,
        &bundle.input_commitment,
        &bundle.challenge,
    )
    .map_err(|e| CpsVerError::LayerVerify(format!("pool: {e}")))?;
    verify_fc_toy(
        &bundle.pi_fc,
        &bundle.model_commitment,
        &bundle.input_commitment,
        &bundle.challenge,
    )
    .map_err(|e| CpsVerError::LayerVerify(format!("fc: {e}")))?;
    let verify_layers_ms = t_layers.elapsed().as_millis();

    let total_ms = t0.elapsed().as_millis();
    Ok(VerifyTiming {
        cm_w_ms,
        verify_layers_ms,
        total_ms,
    })
}

fn w_star_matches_layer_layout(w_star: &[u128], t: &ToyCpsTraces) -> bool {
    ToyWeightLayout::conv_filter(w_star) == t.conv.filter.as_slice()
        && ToyWeightLayout::fc_weights(w_star) == t.fc.weights.as_slice()
        && ToyWeightLayout::fc_bias(w_star) == t.fc.bias.as_slice()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn w_star() -> Vec<u128> {
        vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7]
    }

    fn traces() -> ToyCpsTraces {
        ToyCpsTraces {
            conv: ConvToyTrace {
                filter: vec![1, 0, 1, 2, 0, 2, 1, 0, 1],
                windows: vec![
                    vec![1, 2, 3, 5, 6, 7, 9, 10, 11],
                    vec![2, 3, 4, 6, 7, 8, 10, 11, 12],
                    vec![5, 6, 7, 9, 10, 11, 13, 14, 15],
                    vec![6, 7, 8, 10, 11, 12, 14, 15, 16],
                ],
                outputs: vec![48, 56, 80, 88],
            },
            pool: PoolToyTrace {
                windows: vec![vec![48, 56, 80, 88]],
                outputs: vec![272],
            },
            fc: FcToyTrace {
                input: 272,
                weights: vec![2, 3],
                bias: vec![5, 7],
                outputs: vec![549, 823],
            },
        }
    }

    fn fixed_challenge() -> ClientChallenge {
        ClientChallenge {
            gamma: "11".repeat(32),
            gamma_add: "22".repeat(32),
            gamma_mult: "33".repeat(32),
            num_point_adds: 0,
            num_point_mults: 0,
        }
    }

    #[test]
    fn z6_prove_verify_toy_e2e_honest() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (bundle, _pt) = prove_toy_cps(&w, &t, &c).expect("prove");
        verify_toy_cps_bundle(&bundle, Some(&t)).expect("verify ok");
    }

    #[test]
    fn z6_verify_rejects_tampered_cm_w() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
        bundle.cm_w.cm_hex = "00".repeat(32);
        let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
        assert!(matches!(err, CpsVerError::CmWMismatch(_)), "got {err:?}");
    }

    #[test]
    fn z6_verify_rejects_tampered_w_star_opening() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
        bundle.w_star_opening[0] = bundle.w_star_opening[0].wrapping_add(1);
        let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
        assert!(matches!(err, CpsVerError::CmWMismatch(_)));
    }

    #[test]
    fn z6_verify_rejects_tampered_challenge() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
        bundle.challenge.gamma = "ff".repeat(32);
        let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
        assert!(matches!(err, CpsVerError::LayerVerify(_)));
    }

    #[test]
    fn z6_verify_rejects_tampered_layer_proof_bytes() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
        if let Some(last) = bundle.pi_conv.proof_bytes.last_mut() {
            *last ^= 0xff;
        }
        let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
        assert!(matches!(err, CpsVerError::LayerVerify(_)));
    }

    #[test]
    fn z6_verify_rejects_pedersen_digest_mismatch() {
        let w = w_star();
        let t = traces();
        let c = fixed_challenge();
        let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
        bundle.model_commitment.cm_weights.digest_hex = "ab".repeat(32);
        let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
        assert!(matches!(err, CpsVerError::PedersenDigestMismatch(_)));
    }

    #[test]
    fn z6_prove_rejects_tampered_w_star() {
        let mut w = w_star();
        w[3] = 99;
        let t = traces();
        let c = fixed_challenge();
        let err = prove_toy_cps(&w, &t, &c).expect_err("prove must reject");
        assert!(err.contains("conv filter"), "got {err}");
    }

    #[test]
    fn z6_protocol_w_star_layout_mismatch_rejected() {
        let w = w_star();
        let mut t = traces();
        t.fc.weights[0] = 99;
        let c = fixed_challenge();
        let err = prove_toy_cps(&w, &t, &c).expect_err("trace ↔ W* mismatch");
        assert!(err.contains("fc weights"), "got {err}");
    }
}
