//! Z.9 acceptance: Network A migration of the Phase Z cm_W + EC pipeline.
//!
//! Network A has:
//!   - 1219 weights (Spartan PC padded to 2048 = 2^11 → L_size = 64 PC points).
//!   - 2144 PtAdd witnesses (~315 KB each → ~1.6 MB total per witness JSON).
//!   - 178 PtMul witnesses (~26 KB each).
//!
//! This test only exercises the **cm_W (Spartan PC)** computation for
//! Network A so it runs quickly in CI. Full EC SNARK prove timings are
//! covered by the `prove-with-challenge A` + `VPIN_EC_REAL_PROVE=1` path
//! (see docs/M5-performance-report.md §Z.9).
//!
//! Stop condition: cm_W computation > 30 s ⇒ write
//! `docs/issues/Z-9-network-A-perf.md` and mark blocked.
//!
//! Performance JSON: `vpin-backend/tests/perf/Z-9.json`.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use serde::Deserialize;
use vpin_server_crypto::commit::cps::{cps_comm_w_star, CPS_KIND_SPARTAN_PC};

#[derive(Deserialize)]
struct FullWeightsJson {
    network_id: String,
    num_weights: usize,
    w_star_flat: Vec<String>,
}

fn load_network_a_w_star() -> Result<Vec<u128>, String> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
        .join("src")
        .join("cp-snark-full")
        .join("model_exports")
        .join("A")
        .join("full_weights.json");
    let raw = fs::read_to_string(&path).map_err(|e| format!("read {path:?}: {e}"))?;
    let doc: FullWeightsJson = serde_json::from_str(&raw)
        .map_err(|e| format!("parse {path:?}: {e}"))?;
    if doc.network_id != "A" {
        return Err(format!("network_id {} != A", doc.network_id));
    }
    if doc.num_weights != doc.w_star_flat.len() {
        return Err(format!(
            "num_weights {} != w_star_flat.len() {}",
            doc.num_weights,
            doc.w_star_flat.len()
        ));
    }
    doc.w_star_flat
        .iter()
        .map(|s| s.parse::<u128>().map_err(|e| format!("weight {s}: {e}")))
        .collect()
}

/// Merge cm_W metrics into `tests/perf/Z-9.json` without clobbering the
/// hand-curated EC SNARK fields written by `VPIN_EC_REAL_PROVE=1`
/// (`ec_prove_ms`, `ec_proof_artifact_*`). If the file doesn't exist yet
/// we still produce the cm_W-only payload so CI has a baseline.
fn write_perf_z9(
    num_weights: usize,
    padded_len: usize,
    cm_w_ms: u128,
    poly_comm_count: usize,
    cm_w_hex: &str,
) {
    let perf_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("tests")
        .join("perf");
    fs::create_dir_all(&perf_dir).expect("perf dir");
    let path = perf_dir.join("Z-9.json");
    let mut payload = if let Ok(raw) = fs::read_to_string(&path) {
        serde_json::from_str::<serde_json::Value>(&raw)
            .unwrap_or_else(|_| serde_json::json!({}))
    } else {
        serde_json::json!({})
    };
    let obj = payload.as_object_mut().expect("Z-9 perf is JSON object");
    obj.insert("task".into(), serde_json::Value::String("Z-9".into()));
    obj.insert("network".into(), serde_json::Value::String("A".into()));
    obj.insert("num_weights".into(), serde_json::json!(num_weights));
    obj.insert("padded_len".into(), serde_json::json!(padded_len));
    obj.insert("cm_w_ms".into(), serde_json::json!(cm_w_ms));
    obj.insert("poly_comm_count".into(), serde_json::json!(poly_comm_count));
    obj.insert(
        "cm_w_hex".into(),
        serde_json::Value::String(cm_w_hex.to_string()),
    );
    if !obj.contains_key("ec_prove_status") {
        obj.insert(
            "ec_prove_status".into(),
            serde_json::Value::String(
                "pending — gated on VPIN_EC_REAL_PROVE=1; see docs/M5-performance-report.md".into(),
            ),
        );
    }
    fs::write(&path, serde_json::to_string_pretty(&payload).unwrap()).expect("write Z-9 perf");
}

#[test]
fn z9_network_a_cps_comm_w_star_smoke_and_perf() {
    let weights = load_network_a_w_star().expect("load Network A W*");
    assert_eq!(weights.len(), 1219);

    let t0 = Instant::now();
    let cm = cps_comm_w_star(&weights).expect("cm_W");
    let cm_w_ms = t0.elapsed().as_millis();

    assert_eq!(cm.kind, CPS_KIND_SPARTAN_PC);
    assert_eq!(cm.num_scalars, 1219);
    assert_eq!(cm.padded_len, 2048, "1219 padded to next pow2 = 2048");
    assert_eq!(
        cm.poly_comm_hex.len(),
        32,
        "L_size = 2^(ell/2) with ell = log2(2048) = 11 → L_size = 2^5 = 32"
    );

    write_perf_z9(
        weights.len(),
        cm.padded_len,
        cm_w_ms,
        cm.poly_comm_hex.len(),
        &cm.cm_hex,
    );

    assert!(
        cm_w_ms < 30_000,
        "cm_W computation for Network A must finish in < 30s; got {cm_w_ms}ms"
    );
}

#[test]
fn z9_network_a_cm_w_is_deterministic() {
    let weights = load_network_a_w_star().expect("load");
    let a = cps_comm_w_star(&weights).expect("a");
    let b = cps_comm_w_star(&weights).expect("b");
    assert_eq!(a, b, "Network A cm_W must be deterministic");
}
