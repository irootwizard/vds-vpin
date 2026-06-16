//! Z.6 acceptance: toy CPS.Ver end-to-end.
//!
//! Covers:
//! - Satisfiability: honest W*/traces → bundle verifies + perf written to
//!   `vpin-backend/tests/perf/Z-6.json`.
//! - Negative: tampered cm_W / tampered γ / tampered Pedersen digest /
//!   tampered layer proof → verify returns `Err(CpsVerError::*)`.
//! - Protocol: prove rejects tampered W* (L1 binding).
//! - Cross-crate parity: cm_hex matches the literal computed by Spartan
//!   PC over the canonical toy W* (frozen fact bytes).

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use vpin_server_crypto::challenge::ClientChallenge;
use vpin_server_crypto::circuit::cps_ver::{
    prove_toy_cps, verify_toy_cps_bundle, CpsVerError, ToyCpsTraces,
};
use vpin_server_crypto::circuit::layer::{
    conv_mac::ConvToyTrace, fc_mac::FcToyTrace, pool_sum::PoolToyTrace,
};
use vpin_server_crypto::commit::cps::cps_comm_w_star;

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

fn write_perf_z6(prove_ms: u128, verify_ms: u128, proof_bytes: usize, cm_w_bytes: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).expect("perf dir");
    let payload = serde_json::json!({
        "task": "Z-6",
        "prove_ms": prove_ms,
        "verify_ms": verify_ms,
        "proof_bytes": proof_bytes,
        "cm_w_bytes": cm_w_bytes,
    });
    fs::write(
        perf_dir.join("Z-6.json"),
        serde_json::to_string_pretty(&payload).unwrap(),
    )
    .expect("write perf");
}

#[test]
fn z6_toy_cps_e2e_honest_and_perf() {
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
    let cm_w_bytes = bundle
        .cm_w
        .poly_comm_hex
        .iter()
        .map(|s| s.len() / 2)
        .sum::<usize>();
    write_perf_z6(prove_ms, verify_ms, proof_bytes, cm_w_bytes);

    assert_eq!(bundle.cm_w.kind, "spartan_pc");
    assert_eq!(bundle.cm_w.num_scalars, 13);
}

#[test]
fn z6_verify_rejects_tampered_cm_w() {
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    bundle.cm_w.cm_hex = "00".repeat(32);
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    assert!(matches!(err, CpsVerError::CmWMismatch(_)));
}

#[test]
fn z6_verify_rejects_tampered_challenge() {
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    bundle.challenge.gamma = "ff".repeat(32);
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    assert!(matches!(err, CpsVerError::LayerVerify(_)));
}

#[test]
fn z6_verify_rejects_tampered_w_star_opening() {
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    bundle.w_star_opening[6] = 99;
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    // cm_W differs because the opening changed
    assert!(matches!(err, CpsVerError::CmWMismatch(_)));
}

#[test]
fn z6_verify_rejects_short_opening() {
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    bundle.w_star_opening.pop();
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    assert!(matches!(err, CpsVerError::WStarLength(_)));
}

#[test]
fn z6_verify_rejects_layer_proof_tampering() {
    let w = w_star();
    let t = traces();
    let c = challenge();
    let (mut bundle, _) = prove_toy_cps(&w, &t, &c).expect("prove");
    if let Some(last) = bundle.pi_fc.proof_bytes.last_mut() {
        *last ^= 0xff;
    }
    let err = verify_toy_cps_bundle(&bundle, Some(&t)).expect_err("must reject");
    assert!(matches!(err, CpsVerError::LayerVerify(_)));
}

#[test]
fn z6_protocol_prove_rejects_tampered_filter_in_w_star() {
    let mut w = w_star();
    w[0] = 99;
    let t = traces();
    let c = challenge();
    let err = prove_toy_cps(&w, &t, &c).expect_err("prove must reject");
    assert!(err.contains("conv filter"), "got {err}");
}

/// Frozen toy-W* digest produced by both `vpin-server-crypto::commit::cps`
/// and `cp_snark_full::commit::cps::cps_comm_w_star`. Captured once from
/// the reference implementation; any divergence between the two crates or
/// the underlying Spartan PC parameters will flip this byte string.
pub const TOY_W_STAR_CM_HEX: &str =
    "d056527f12aad5b2200a98e5e882c15d7dac17ed234ffa6352cd2e633b346645";

#[test]
fn z6_cross_crate_cm_hex_stability() {
    let cm = cps_comm_w_star(&w_star()).expect("cm_w");
    assert_eq!(cm.padded_len, 16);
    assert_eq!(cm.num_scalars, 13);
    assert_eq!(cm.poly_comm_hex.len(), 4); // L_size = 2^(ell/2) = 2^2 = 4
    assert_eq!(cm.cm_hex.len(), 64); // SHA-256 hex
    assert_eq!(
        cm.cm_hex, TOY_W_STAR_CM_HEX,
        "cm_hex must match the frozen reference vector"
    );
}
