//! Z.3 acceptance tests for the toy FC MAC + bias R1CS (Eq. 10).

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use vpin_server_crypto::challenge::ClientChallenge;
use vpin_server_crypto::circuit::layer::fc_mac::{prove_fc_toy, verify_fc_toy, FcToyTrace};
use vpin_server_crypto::commit::{commit_model, commit_public_inputs};
use vpin_server_crypto::curve::embed_u128_to_scalar;

fn toy_trace() -> FcToyTrace {
    FcToyTrace {
        input: 272,
        weights: vec![2, 3],
        bias: vec![5, 7],
        outputs: vec![549, 823],
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
    let weights: Vec<u128> = vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7];
    let (model, _, _) = commit_model(&weights);
    let trace = toy_trace();
    let (input, _) = commit_public_inputs(&[embed_u128_to_scalar(trace.input)]);
    (model, input)
}

fn write_perf(name: &str, prove_ms: u128, verify_ms: u128, proof_bytes: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).unwrap();
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
    .unwrap();
}

#[test]
fn fc_toy_prove_verify_roundtrip_honest() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (proof, prove_ms) = prove_fc_toy(&trace, &model, &input, &challenge).expect("prove");
    let t0 = Instant::now();
    verify_fc_toy(&proof, &model, &input, &challenge).expect("verify");
    write_perf("Z-3", prove_ms, t0.elapsed().as_millis(), proof.proof_bytes.len());
}

#[test]
fn fc_toy_rejects_wrong_challenge() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (proof, _) = prove_fc_toy(&trace, &model, &input, &challenge).expect("prove");
    let mut bad = challenge.clone();
    bad.gamma = "ff".repeat(32);
    assert!(verify_fc_toy(&proof, &model, &input, &bad).is_err());
}

#[test]
fn fc_toy_rejects_tampered_proof_bytes() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (mut proof, _) = prove_fc_toy(&trace, &model, &input, &challenge).expect("prove");
    if let Some(last) = proof.proof_bytes.last_mut() {
        *last ^= 0xff;
    }
    assert!(verify_fc_toy(&proof, &model, &input, &challenge).is_err());
}

#[test]
fn fc_toy_rejects_wrong_model_commitment() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (proof, _) = prove_fc_toy(&trace, &model, &input, &challenge).expect("prove");
    let mut bad_model = model.clone();
    bad_model.cm_weights.point_hex = "ab".repeat(32);
    assert!(verify_fc_toy(&proof, &bad_model, &input, &challenge).is_err());
}

#[test]
fn fc_toy_prove_rejects_wrong_weight_witness() {
    let mut bad = toy_trace();
    bad.weights[0] = 99;
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let res = prove_fc_toy(&bad, &model, &input, &challenge);
    assert!(matches!(res, Err(ref e) if e.contains("unsatisfied")));
}

#[test]
fn fc_toy_prove_rejects_wrong_bias_witness() {
    let mut bad = toy_trace();
    bad.bias[1] = 0;
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let res = prove_fc_toy(&bad, &model, &input, &challenge);
    assert!(matches!(res, Err(ref e) if e.contains("unsatisfied")));
}

#[test]
fn fc_toy_protocol_rejects_circuit_name_mismatch() {
    let trace = toy_trace();
    let (model, input) = toy_commitments();
    let challenge = fixed_challenge();
    let (mut proof, _) = prove_fc_toy(&trace, &model, &input, &challenge).expect("prove");
    proof.circuit_name = "spoof_fc".to_string();
    assert!(verify_fc_toy(&proof, &model, &input, &challenge).is_err());
}
