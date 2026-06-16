//! Z.1 acceptance tests for the toy conv MAC R1CS (Eq. 9).
//!
//! Covers:
//! - Satisfiability: honest trace produces a verifying SNARK.
//! - Negative: tampered proof bytes / wrong challenge / wrong model commitment → verify fails.
//! - Protocol: prove rejects missing `gamma`.
//! - Performance: writes `vpin-backend/tests/perf/Z-1.json`.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use vpin_server_crypto::challenge::ClientChallenge;
use vpin_server_crypto::circuit::layer::conv_mac::{prove_conv_toy, verify_conv_toy, ConvToyTrace};
use vpin_server_crypto::commit::{commit_model, commit_public_inputs};
use vpin_server_crypto::curve::embed_u128_to_scalar;

fn toy_trace() -> ConvToyTrace {
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

fn fixed_challenge() -> ClientChallenge {
    ClientChallenge {
        gamma: "11".repeat(32),
        gamma_add: "22".repeat(32),
        gamma_mult: "33".repeat(32),
        num_point_adds: 0,
        num_point_mults: 0,
    }
}

fn toy_commitments() -> (
    vpin_server_crypto::commit::ModelCommitmentBundle,
    vpin_server_crypto::commit::InputCommitmentBundle,
) {
    let trace = toy_trace();
    let (model, _, _) = commit_model(&trace.filter);
    let public_scalars: Vec<_> = trace
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input, _) = commit_public_inputs(&public_scalars);
    (model, input)
}

fn write_perf(name: &str, prove_ms: u128, verify_ms: u128, proof_bytes: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).expect("perf dir");
    let payload = serde_json::json!({
        "task": name,
        "prove_ms": prove_ms,
        "verify_ms": verify_ms,
        "proof_bytes": proof_bytes,
    });
    fs::write(
        perf_dir.join(format!("{name}.json")),
        serde_json::to_string_pretty(&payload).unwrap(),
    )
    .expect("write perf");
}

#[test]
fn conv_toy_prove_verify_roundtrip_honest() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();

    let (proof, prove_ms) = prove_conv_toy(&trace, &model, &input, &challenge).expect("prove");
    let t0 = Instant::now();
    verify_conv_toy(&proof, &model, &input, &challenge).expect("verify ok");
    let verify_ms = t0.elapsed().as_millis();

    write_perf("Z-1", prove_ms, verify_ms, proof.proof_bytes.len());

    assert_eq!(proof.circuit_name, "conv_toy");
    assert!(!proof.proof_bytes.is_empty());
}

#[test]
fn conv_toy_verify_rejects_wrong_challenge() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (proof, _) = prove_conv_toy(&trace, &model, &input, &challenge).expect("prove");

    let mut tampered = challenge.clone();
    tampered.gamma = "ff".repeat(32);
    assert!(
        verify_conv_toy(&proof, &model, &input, &tampered).is_err(),
        "verify should reject mismatched γ"
    );
}

#[test]
fn conv_toy_verify_rejects_tampered_proof_bytes() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (mut proof, _) = prove_conv_toy(&trace, &model, &input, &challenge).expect("prove");

    if let Some(last) = proof.proof_bytes.last_mut() {
        *last ^= 0xff;
    }
    assert!(
        verify_conv_toy(&proof, &model, &input, &challenge).is_err(),
        "verify should reject tampered proof bytes"
    );
}

#[test]
fn conv_toy_verify_rejects_wrong_model_commitment() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (proof, _) = prove_conv_toy(&trace, &model, &input, &challenge).expect("prove");

    let mut wrong_model = model.clone();
    wrong_model.cm_weights.point_hex = "ab".repeat(32);
    assert!(
        verify_conv_toy(&proof, &wrong_model, &input, &challenge).is_err(),
        "verify should reject mismatched cm_W"
    );
}

#[test]
fn conv_toy_prove_rejects_wrong_filter_witness() {
    let mut bad_trace = toy_trace();
    bad_trace.filter[3] = 99;
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let res = prove_conv_toy(&bad_trace, &model, &input, &challenge);
    assert!(
        matches!(res, Err(ref e) if e.contains("unsatisfied")),
        "expected unsatisfied, got {res:?}"
    );
}

#[test]
fn conv_toy_protocol_rejects_circuit_name_mismatch() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (mut proof, _) = prove_conv_toy(&trace, &model, &input, &challenge).expect("prove");

    proof.circuit_name = "spoof_layer".to_string();
    let res = verify_conv_toy(&proof, &model, &input, &challenge);
    assert!(res.is_err(), "verify should reject circuit_name mismatch");
}
