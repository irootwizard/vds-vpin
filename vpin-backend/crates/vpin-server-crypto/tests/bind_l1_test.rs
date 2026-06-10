//! Z.4 acceptance tests for L1 weight binding.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use vpin_server_crypto::challenge::ClientChallenge;
use vpin_server_crypto::circuit::bind_l1::{
    check_l1_binding, prove_toy_with_binding, ToyWeightLayout,
};
use vpin_server_crypto::circuit::layer::conv_mac::{verify_conv_toy, ConvToyTrace};
use vpin_server_crypto::circuit::layer::fc_mac::{verify_fc_toy, FcToyTrace};
use vpin_server_crypto::circuit::layer::pool_sum::{verify_pool_toy, PoolToyTrace};
use vpin_server_crypto::commit::{commit_model, commit_public_inputs};
use vpin_server_crypto::curve::embed_u128_to_scalar;

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

fn pool_trace() -> PoolToyTrace {
    PoolToyTrace {
        windows: vec![vec![48, 56, 80, 88]],
        outputs: vec![272],
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

fn fixed_challenge() -> ClientChallenge {
    ClientChallenge {
        gamma: "11".repeat(32),
        gamma_add: "22".repeat(32),
        gamma_mult: "33".repeat(32),
        num_point_adds: 0,
        num_point_mults: 0,
    }
}

fn write_perf(name: &str, total_prove_ms: u128, verify_ms: u128, total_proof_bytes: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).unwrap();
    let payload = serde_json::json!({
        "task": name,
        "prove_ms": total_prove_ms,
        "verify_ms": verify_ms,
        "proof_bytes": total_proof_bytes,
    });
    fs::write(
        perf_dir.join(format!("{name}.json")),
        serde_json::to_string_pretty(&payload).unwrap(),
    )
    .unwrap();
}

#[test]
fn z4_toy_layout_constants_are_stable() {
    assert_eq!(ToyWeightLayout::CONV_FILTER_RANGE, 0..9);
    assert_eq!(ToyWeightLayout::FC_WEIGHTS_RANGE, 9..11);
    assert_eq!(ToyWeightLayout::FC_BIAS_RANGE, 11..13);
}

#[test]
fn z4_prove_toy_with_binding_honest_w_star() {
    let w = w_star();
    let (model, _, _) = commit_model(&w);
    let public_scalars: Vec<_> = conv_trace()
        .windows
        .iter()
        .flatten()
        .copied()
        .map(embed_u128_to_scalar)
        .collect();
    let (input, _) = commit_public_inputs(&public_scalars);
    let chal = fixed_challenge();

    let bundle = prove_toy_with_binding(
        &w,
        &conv_trace(),
        &pool_trace(),
        &fc_trace(),
        &model,
        &input,
        &chal,
    )
    .expect("honest prove");

    let t0 = Instant::now();
    verify_conv_toy(&bundle.pi_conv, &model, &input, &chal).expect("conv verify");
    verify_pool_toy(&bundle.pi_pool, &model, &input, &chal).expect("pool verify");
    verify_fc_toy(&bundle.pi_fc, &model, &input, &chal).expect("fc verify");
    let verify_ms = t0.elapsed().as_millis();

    let total_prove_ms = bundle.prove_ms_conv + bundle.prove_ms_pool + bundle.prove_ms_fc;
    let total_proof_bytes = bundle.pi_conv.proof_bytes.len()
        + bundle.pi_pool.proof_bytes.len()
        + bundle.pi_fc.proof_bytes.len();
    write_perf("Z-4", total_prove_ms, verify_ms, total_proof_bytes);
}

#[test]
fn z4_prove_fails_when_w_star_filter_tampered() {
    let mut w = w_star();
    w[3] = 99;
    let (model, _, _) = commit_model(&w);
    let (input, _) = commit_public_inputs(&[]);
    let chal = fixed_challenge();
    let res = prove_toy_with_binding(
        &w,
        &conv_trace(),
        &pool_trace(),
        &fc_trace(),
        &model,
        &input,
        &chal,
    );
    assert!(
        matches!(res, Err(ref e) if e.contains("conv filter")),
        "tampered conv filter should fail bind, got {res:?}"
    );
}

#[test]
fn z4_prove_fails_when_w_star_fc_weight_tampered() {
    let mut w = w_star();
    w[9] = 0;
    let (model, _, _) = commit_model(&w);
    let (input, _) = commit_public_inputs(&[]);
    let chal = fixed_challenge();
    let res = prove_toy_with_binding(
        &w,
        &conv_trace(),
        &pool_trace(),
        &fc_trace(),
        &model,
        &input,
        &chal,
    );
    assert!(
        matches!(res, Err(ref e) if e.contains("fc weights")),
        "tampered fc weight should fail bind, got {res:?}"
    );
}

#[test]
fn z4_prove_fails_when_w_star_fc_bias_tampered() {
    let mut w = w_star();
    w[12] = 0;
    let (model, _, _) = commit_model(&w);
    let (input, _) = commit_public_inputs(&[]);
    let chal = fixed_challenge();
    let res = prove_toy_with_binding(
        &w,
        &conv_trace(),
        &pool_trace(),
        &fc_trace(),
        &model,
        &input,
        &chal,
    );
    assert!(
        matches!(res, Err(ref e) if e.contains("fc bias")),
        "tampered fc bias should fail bind, got {res:?}"
    );
}

#[test]
fn z4_binding_check_passes_for_honest_w_star() {
    check_l1_binding(&w_star(), &conv_trace(), &fc_trace()).expect("honest binding");
}
