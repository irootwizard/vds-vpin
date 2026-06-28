use serde_json::Value;
use std::path::{Path, PathBuf};
use std::{fs::File, io::Read, str::FromStr};

use crate::witness::active_ec_witness_root;

fn legacy_rust_files_base(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../proof_generation/vPIN_proof_generation/src/rust_files")
        .join(network)
}

fn resolve_ec_root() -> Result<PathBuf, String> {
    if let Some(root) = active_ec_witness_root() {
        return Ok(root);
    }
    if std::env::var("VPIN_ALLOW_LEGACY_WITNESS").ok().as_deref() == Some("1") {
        return Ok(PathBuf::new()); // sentinel: use legacy per-network path
    }
    Err(
        "EC witness root not set: set VPIN_EC_WITNESS_ROOT, call set_active_ec_witness_root, \
         or ProofPlan::activate_witness before load_data"
            .into(),
    )
}

fn point_mult_dir(network: &str) -> Result<PathBuf, String> {
    let root = resolve_ec_root()?;
    if root.as_os_str().is_empty() {
        return Ok(legacy_rust_files_base(network).join("pointMult"));
    }
    Ok(root.join("pointMult"))
}

fn point_add_dir(network: &str) -> Result<PathBuf, String> {
    let root = resolve_ec_root()?;
    if root.as_os_str().is_empty() {
        return Ok(legacy_rust_files_base(network).join("pointAdd"));
    }
    Ok(root.join("pointAdd"))
}

fn read_weight_json(path: &Path) -> Result<Vec<u128>, String> {
    let mut file = File::open(path).map_err(|e| format!("{path:?}: {e}"))?;
    let mut contents = String::new();
    file.read_to_string(&mut contents)
        .map_err(|e| format!("read {:?}: {e}", path))?;
    let parsed: Vec<String> = serde_json::from_str(&contents).map_err(|e| e.to_string())?;
    parsed
        .into_iter()
        .map(|weight_str| {
            u128::from_str(weight_str.as_str())
                .map_err(|e| format!("parse weight {weight_str}: {e}"))
        })
        .collect()
}

fn read_matrix(path: &Path) -> Result<Vec<Vec<i64>>, String> {
    let mut file = File::open(path).map_err(|e| format!("{path:?}: {e}"))?;
    let mut contents = String::new();
    file.read_to_string(&mut contents)
        .map_err(|e| format!("read {:?}: {e}", path))?;
    let parsed: Vec<Vec<Value>> = serde_json::from_str(&contents).map_err(|e| e.to_string())?;
    Ok(parsed
        .into_iter()
        .map(|row| row.into_iter().filter_map(|v| v.as_i64()).collect())
        .collect())
}

/// Load PtMul witness from active `EcWitnessBundle` root (or legacy when `VPIN_ALLOW_LEGACY_WITNESS=1`).
pub fn load_data(network: &str) -> Result<(usize, Vec<u128>, Vec<Vec<i64>>, Vec<Vec<i64>>, usize), String> {
    let pm = point_mult_dir(network)?;
    let file1_path = pm.join("weight.json");
    let file2_path = pm.join("point_mult_px_byte.json");
    let file3_path = pm.join("point_mult_py_byte.json");

    let weights = read_weight_json(&file1_path)?;
    let weights_len = weights.len();
    let point_mult_x_byte = read_matrix(&file2_path)?;
    let point_mult_y_byte = read_matrix(&file3_path)?;

    Ok((weights_len, weights, point_mult_x_byte, point_mult_y_byte, 128))
}

pub fn load_weights_only(network: &str) -> Result<Vec<u128>, String> {
    let (_, weights, _, _, _) = load_data(network)?;
    Ok(weights)
}

/// Legacy infallible API — only for tests with `VPIN_ALLOW_LEGACY_WITNESS=1`.
#[deprecated(note = "use load_data() Result API with EcWitnessBundle")]
pub fn load_data_legacy(network: &str) -> (usize, Vec<u128>, Vec<Vec<i64>>, Vec<Vec<i64>>, usize) {
    std::env::set_var("VPIN_ALLOW_LEGACY_WITNESS", "1");
    load_data(network).expect("load_data_legacy")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::witness::set_active_ec_witness_root;

    #[test]
    fn load_from_run_ec_witness() {
        let run = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../model_training/outputs/20260622_184254");
        let ec = run.join("proof_artifacts").join("ec_witness");
        if !ec.join("pointMult").join("weight.json").is_file() {
            return;
        }
        set_active_ec_witness_root(Some(ec));
        let (n, _, _, _, _) = load_data("A").unwrap();
        assert_eq!(n, 178);
        set_active_ec_witness_root(None);
    }
}
