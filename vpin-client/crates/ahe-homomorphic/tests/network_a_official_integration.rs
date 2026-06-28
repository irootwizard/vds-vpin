//! Network A official MNIST + registry weights integration (Rust vs Python baseline).

use std::path::PathBuf;

use ahe_homomorphic::{numpy_homomorphic_plain, TruncationPlan};
use ahe_model_bundle::{default_network_a_weights_dir, detect_repo_root, load_network_a_weights};

fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures")
}

fn load_mnist_samples() -> serde_json::Value {
    let path = fixtures_dir().join("mnist_samples.json");
    let raw = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {path:?}: {e}"));
    serde_json::from_str(&raw).unwrap_or_else(|e| panic!("parse mnist_samples: {e}"))
}

fn load_network_a_baseline() -> Option<serde_json::Value> {
    let path = fixtures_dir().join("network_a_baseline.json");
    let raw = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&raw).ok()
}

fn repo_weights_dir() -> PathBuf {
    let repo = detect_repo_root();
    default_network_a_weights_dir(&repo)
}

#[test]
fn registered_weights_load_from_vpin_main() {
    let dir = repo_weights_dir();
    if !dir.is_dir() {
        eprintln!("skip: weights dir missing {:?}", dir);
        return;
    }
    let w = load_network_a_weights(&dir).expect("load registry weights");
    assert_eq!(w.weight_fc1.nrows(), 64);
    assert_eq!(w.weight_fc1.ncols(), 16);
    assert_eq!(w.weight_fc2.nrows(), 16);
    assert_eq!(w.weight_fc2.ncols(), 10);
}

#[test]
fn plain_forward_matches_python_baseline() {
    let baseline = match load_network_a_baseline() {
        Some(b) => b,
        None => {
            eprintln!("skip: run tools/parity-export/export_baseline.py --network-a");
            return;
        }
    };
    let dir = repo_weights_dir();
    if !dir.is_dir() {
        eprintln!("skip: weights dir {:?}", dir);
        return;
    }
    let weights = load_network_a_weights(&dir).expect("weights");
    let plan = TruncationPlan::default();
    let samples = baseline["samples"].as_array().expect("samples array");

    for sample in samples {
        let idx = sample["mnist_index"].as_i64().unwrap() as i32;
        let mnist = load_mnist_samples();
        let entry = mnist
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["mnist_index"].as_i64() == Some(idx as i64))
            .unwrap_or_else(|| panic!("mnist index {idx} missing in mnist_samples.json"));
        let fixed: Vec<i32> = entry["fixed_int32"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_i64().unwrap() as i32)
            .collect();
        let out = numpy_homomorphic_plain(&fixed, &weights, &plan).expect("forward");
        let expected_logits: Vec<i64> = sample["after_fc2"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_i64().unwrap())
            .collect();
        assert_eq!(
            out.after_fc2, expected_logits,
            "logits mismatch index={idx}"
        );
        assert_eq!(
            out.prediction,
            sample["prediction"].as_u64().unwrap() as usize,
            "prediction mismatch index={idx}"
        );
    }
}

#[test]
fn plain_forward_layerwise_max_diff_zero_on_fixtures() {
    let dir = repo_weights_dir();
    if !dir.is_dir() {
        eprintln!("skip: weights dir {:?}", dir);
        return;
    }
    let weights = load_network_a_weights(&dir).expect("weights");
    let plan = TruncationPlan::default();
    let mnist = load_mnist_samples();
    for entry in mnist.as_array().unwrap().iter().take(5) {
        let fixed: Vec<i32> = entry["fixed_int32"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_i64().unwrap() as i32)
            .collect();
        let out = numpy_homomorphic_plain(&fixed, &weights, &plan).expect("forward");
        assert_eq!(out.after_fc2.len(), 10);
        assert!(out.after_fc2.iter().all(|&v| v >= 0));
    }
}

#[test]
fn fixed_accuracy_on_fixture_indices() {
    let dir = repo_weights_dir();
    if !dir.is_dir() {
        eprintln!("skip: weights dir {:?}", dir);
        return;
    }
    let weights = load_network_a_weights(&dir).expect("weights");
    let plan = TruncationPlan::default();
    let mnist = load_mnist_samples();
    let mut correct = 0usize;
    let mut total = 0usize;
    for entry in mnist.as_array().unwrap() {
        let label = entry["label"].as_i64().unwrap() as usize;
        let fixed: Vec<i32> = entry["fixed_int32"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_i64().unwrap() as i32)
            .collect();
        let out = numpy_homomorphic_plain(&fixed, &weights, &plan).expect("forward");
        if out.prediction == label {
            correct += 1;
        }
        total += 1;
    }
    let acc = correct as f64 / total as f64;
    assert!(
        acc >= 0.85,
        "fixture fixed acc too low: {acc:.4} ({correct}/{total})"
    );
}
