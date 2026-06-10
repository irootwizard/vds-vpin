//! Z.5 acceptance: end-to-end Spartan PC `cps_comm_w_star`.
//!
//! Covers:
//! - Satisfiability: toy `W*` (13 scalars) commits and a fresh commit matches.
//! - Negative: empty input → `InvalidInput`; tampered `W*` → different cm_hex.
//! - Protocol: kind tag is `spartan_pc` and structurally distinct from Pedersen.
//! - Performance: writes `vpin-backend/tests/perf/Z-5.json` for the toy
//!   commitment timing & on-wire bytes.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use cp_snark_full::commit::cps::{
    commit_model_pedersen_for_diff, cps_comm_w_star, time_cps_comm_w_star, CpsError,
    CPS_KIND_SPARTAN_PC,
};

fn toy_w_star() -> Vec<u128> {
    vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 3, 5, 7, 11]
}

fn write_perf_z5(prove_ms: u128, verify_ms: u128, commitment_bytes: usize, num_scalars: usize) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("vpin-backend")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).expect("perf dir");
    let payload = serde_json::json!({
        "task": "Z-5",
        "prove_ms": prove_ms,
        "verify_ms": verify_ms,
        "commitment_bytes": commitment_bytes,
        "num_scalars": num_scalars,
        "kind": CPS_KIND_SPARTAN_PC,
    });
    fs::write(
        perf_dir.join("Z-5.json"),
        serde_json::to_string_pretty(&payload).unwrap(),
    )
    .expect("write perf");
}

#[test]
fn z5_toy_cps_comm_w_star_smoke_and_perf() {
    let w = toy_w_star();
    let (prove_ms, bytes) = time_cps_comm_w_star(&w).expect("time toy cps_comm");

    let cm = cps_comm_w_star(&w).expect("toy cm_W");
    let t0 = Instant::now();
    let cm_again = cps_comm_w_star(&w).expect("toy cm_W again");
    let verify_ms = t0.elapsed().as_millis();
    assert_eq!(cm, cm_again, "deterministic Spartan PC");
    assert_eq!(cm.kind, CPS_KIND_SPARTAN_PC);
    assert_eq!(cm.num_scalars, w.len());
    assert_eq!(cm.padded_len, 16);
    assert!(cm.poly_comm_hex.len() >= 1);
    let total: usize = cm.poly_comm_hex.iter().map(|s| s.len() / 2).sum();
    assert_eq!(bytes, total);

    write_perf_z5(prove_ms, verify_ms, bytes, w.len());
}

#[test]
fn z5_negative_empty_rejected() {
    let err = cps_comm_w_star(&[]).unwrap_err();
    match err {
        CpsError::InvalidInput(m) => assert!(m.contains("empty")),
        other => panic!("expected InvalidInput, got {other:?}"),
    }
}

#[test]
fn z5_negative_tampered_w_star_changes_cm_hex() {
    let mut w = toy_w_star();
    let base = cps_comm_w_star(&w).expect("base");
    w[7] = w[7].wrapping_add(1);
    let tampered = cps_comm_w_star(&w).expect("tampered");
    assert_ne!(base.cm_hex, tampered.cm_hex);
    assert_ne!(base.poly_comm_hex, tampered.poly_comm_hex);
}

#[test]
fn z5_protocol_pc_kind_is_spartan_not_pedersen() {
    let w = toy_w_star();
    let pc = cps_comm_w_star(&w).expect("pc");
    let ped = commit_model_pedersen_for_diff(&w);
    assert_eq!(pc.kind, CPS_KIND_SPARTAN_PC);
    assert_ne!(pc.kind, "pedersen");
    assert_ne!(pc.cm_hex, ped, "Spartan PC digest ≠ Pedersen point_hex");
}

#[test]
fn z5_protocol_padding_is_power_of_two() {
    for &(n, expected) in &[(1usize, 1usize), (3, 4), (13, 16), (33, 64)] {
        let w: Vec<u128> = (1..=n as u128).collect();
        let cm = cps_comm_w_star(&w).expect("commit");
        assert_eq!(cm.padded_len, expected, "n={n}");
        assert_eq!(cm.num_scalars, n);
    }
}
