//! Z.8 acceptance: EC and layer proofs share a unified transcript that
//! binds the canonical Spartan PC `cm_W`.
//!
//! Covers:
//! - Satisfiability: when prover and verifier supply the **same** cm_W,
//!   each layer SubCircuitProof verifies.
//! - Negative: tampering cm_W on the verifier side breaks the per-layer
//!   transcript and verification fails (cm_W bound at the front of the
//!   transcript via `seed_layer_transcript`).
//! - Negative: a proof produced with `cps_cm_w = Some(...)` fails to
//!   verify when checked with `cps_cm_w = None` (legacy transcript).
//! - Protocol: `vpin_ec_real_prove_requested()` honors the
//!   `VPIN_EC_REAL_PROVE=1` env var.
//! - Performance: writes `vpin-backend/tests/perf/Z-8.json`.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use vpin_server_crypto::challenge::ClientChallenge;
use vpin_server_crypto::circuit::cps_ver::{
    prove_toy_cps, verify_toy_cps_bundle, CpsVerError, ToyCpsTraces,
};
use vpin_server_crypto::circuit::layer::{
    conv_mac::{prove_conv_toy_with_cm_w, verify_conv_toy, verify_conv_toy_with_cm_w, ConvToyTrace},
    fc_mac::FcToyTrace,
    pool_sum::PoolToyTrace,
};
use vpin_server_crypto::commit::cps::{cps_comm_w_star, CpsCommitment};
use vpin_server_crypto::commit::{commit_model, commit_public_inputs};
use vpin_server_crypto::curve::embed_u128_to_scalar;
use vpin_server_crypto::prove::ec::vpin_ec_real_prove_requested;

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

fn challenge() -> ClientChallenge {
    ClientChallenge {
        gamma: "11".repeat(32),
        gamma_add: "22".repeat(32),
        gamma_mult: "33".repeat(32),
        num_point_adds: 0,
        num_point_mults: 0,
    }
}

fn alt_cm_w() -> CpsCommitment {
    // Different W* -> different cm_W. Spartan PC binding is deterministic
    // so this commitment digest is stable.
    let alt: Vec<u128> = vec![9, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7];
    cps_comm_w_star(&alt).expect("alt cm_w")
}

fn write_perf_z8(prove_ms: u128, verify_ms: u128, proof_bytes: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).expect("perf dir");
    let payload = serde_json::json!({
        "task": "Z-8",
        "prove_ms": prove_ms,
        "verify_ms": verify_ms,
        "proof_bytes": proof_bytes,
        "transcript_binding": "cps_cm_w + pedersen_cm_w + cm_x + challenge + sub_circuit",
    });
    fs::write(
        perf_dir.join("Z-8.json"),
        serde_json::to_string_pretty(&payload).unwrap(),
    )
    .expect("write perf");
}

#[test]
fn z8_toy_cps_bundle_uses_unified_transcript_and_perf() {
    let w = w_star();
    let t = traces();
    let c = challenge();

    let t_prove = Instant::now();
    let (bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    let prove_ms = t_prove.elapsed().as_millis();

    let t_verify = Instant::now();
    verify_toy_cps_bundle(&bundle, Some(&t)).expect("verify ok");
    let verify_ms = t_verify.elapsed().as_millis();

    let proof_bytes = bundle.pi_conv.proof_bytes.len()
        + bundle.pi_pool.proof_bytes.len()
        + bundle.pi_fc.proof_bytes.len();
    write_perf_z8(prove_ms, verify_ms, proof_bytes);
}

#[test]
fn z8_layer_proof_rejects_legacy_transcript_verifier() {
    // Prove a conv layer WITH cm_W in transcript; verify WITHOUT cm_W
    // (None) — the legacy seed differs, so Spartan must reject.
    let w = w_star();
    let cm_w = cps_comm_w_star(&w).expect("cm_w");
    let t = traces();
    let (model, _, _) = commit_model(&w);
    let public_scalars: Vec<_> = t
        .conv
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input, _) = commit_public_inputs(&public_scalars);
    let c = challenge();

    let (proof, _) = prove_conv_toy_with_cm_w(&t.conv, Some(&cm_w), &model, &input, &c)
        .expect("prove with cm_w");

    // Verifier passes `None` for cm_w (legacy seed) — transcript mismatch.
    assert!(
        verify_conv_toy(&proof, &model, &input, &c).is_err(),
        "legacy verifier must reject a cm_w-bound proof"
    );
    // Same verifier with the correct cm_w accepts.
    verify_conv_toy_with_cm_w(&proof, Some(&cm_w), &model, &input, &c)
        .expect("verify with cm_w");
}

#[test]
fn z8_layer_proof_rejects_alternate_cm_w() {
    // Prove with the genuine cm_W; verify with an alternate cm_W
    // (different W*). Transcript no longer matches, so Spartan rejects.
    let w = w_star();
    let cm_w = cps_comm_w_star(&w).expect("cm_w");
    let other = alt_cm_w();
    let t = traces();
    let (model, _, _) = commit_model(&w);
    let public_scalars: Vec<_> = t
        .conv
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input, _) = commit_public_inputs(&public_scalars);
    let c = challenge();

    let (proof, _) = prove_conv_toy_with_cm_w(&t.conv, Some(&cm_w), &model, &input, &c)
        .expect("prove");
    assert!(
        verify_conv_toy_with_cm_w(&proof, Some(&other), &model, &input, &c).is_err(),
        "verifier with foreign cm_w must reject"
    );
}

#[test]
fn z8_verify_toy_cps_rejects_swapped_cm_w_in_bundle() {
    // Swap bundle.cm_w to a different commitment *and* keep the layer
    // proofs intact. verify_toy_cps_bundle catches this at the cm_W
    // recomputation step (CpsVerError::CmWMismatch), not at the layer
    // SNARK level — but the layer SNARK would *also* reject it because
    // the transcript no longer matches.
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    bundle.cm_w = alt_cm_w();
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    assert!(matches!(err, CpsVerError::CmWMismatch(_)), "got {err:?}");
}

#[test]
fn z8_vpin_ec_real_prove_env_var_honored_on_toy() {
    // Test that the env-var gate is observable from Rust code. We can't
    // build EC witness for the toy network, so we just probe the function
    // before and after toggling the env var.
    std::env::remove_var("VPIN_EC_REAL_PROVE");
    assert!(
        !vpin_ec_real_prove_requested(),
        "default: real prove not requested"
    );
    std::env::set_var("VPIN_EC_REAL_PROVE", "1");
    assert!(
        vpin_ec_real_prove_requested(),
        "VPIN_EC_REAL_PROVE=1 must be honored"
    );
    std::env::set_var("VPIN_EC_REAL_PROVE", "0");
    assert!(
        !vpin_ec_real_prove_requested(),
        "VPIN_EC_REAL_PROVE=0 must disable"
    );
    std::env::remove_var("VPIN_EC_REAL_PROVE");
}

#[test]
fn z8_legacy_layer_prove_and_legacy_verify_still_match() {
    // Backwards compat: prove with cps_cm_w = None and verify with
    // cps_cm_w = None still works (Z.1-Z.4 era path).
    let t = traces();
    let (model, _, _) = commit_model(&t.conv.filter);
    let public_scalars: Vec<_> = t
        .conv
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input, _) = commit_public_inputs(&public_scalars);
    let c = challenge();

    let (proof, _) =
        prove_conv_toy_with_cm_w(&t.conv, None, &model, &input, &c).expect("prove legacy");
    verify_conv_toy(&proof, &model, &input, &c).expect("legacy verify");
}
