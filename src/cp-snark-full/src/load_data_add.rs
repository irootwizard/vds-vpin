use std::path::PathBuf;

use serde_json::Value;
use std::{fs::File, io::Read};

use crate::witness::active_ec_witness_root;

fn legacy_rust_files_base(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../proof_generation/vPIN_proof_generation/src/rust_files")
        .join(network)
}

fn point_add_dir(network: &str) -> Result<PathBuf, String> {
    if let Some(root) = active_ec_witness_root() {
        return Ok(root.join("pointAdd"));
    }
    if std::env::var("VPIN_ALLOW_LEGACY_WITNESS").ok().as_deref() == Some("1") {
        return Ok(legacy_rust_files_base(network).join("pointAdd"));
    }
    Err("EC witness root not set for load_data_add".into())
}

fn read_matrix(path: &PathBuf) -> Result<Vec<Vec<i64>>, String> {
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

pub fn load_data_add(
    network: &str,
) -> Result<
    (
        usize,
        Vec<Vec<i64>>,
        Vec<Vec<i64>>,
        Vec<Vec<i64>>,
        Vec<Vec<i64>>,
        Vec<i64>,
    ),
    String,
> {
    let base = point_add_dir(network)?;
    let file1_path = base.join("point_add_px_byte.json");
    let file2_path = base.join("point_add_py_byte.json");
    let file3_path = base.join("point_add_rx_byte.json");
    let file4_path = base.join("point_add_ry_byte.json");
    let file5_path = base.join("point_add_rz_byte.json");

    let point_add_px_byte = read_matrix(&file1_path)?;
    let len = point_add_px_byte.len();
    let point_add_py_byte = read_matrix(&file2_path)?;
    let point_add_rx_byte = read_matrix(&file3_path)?;
    let point_add_ry_byte = read_matrix(&file4_path)?;

    let mut file5 = File::open(&file5_path).map_err(|e| format!("{file5_path:?}: {e}"))?;
    let mut contents5 = String::new();
    file5
        .read_to_string(&mut contents5)
        .map_err(|e| format!("read rz: {e}"))?;
    let parsed5: Vec<Value> = serde_json::from_str(&contents5).map_err(|e| e.to_string())?;
    let point_add_rz_byte: Vec<i64> = parsed5.into_iter().filter_map(|v| v.as_i64()).collect();

    Ok((
        len,
        point_add_px_byte,
        point_add_py_byte,
        point_add_rx_byte,
        point_add_ry_byte,
        point_add_rz_byte,
    ))
}

#[deprecated(note = "use load_data_add() Result API with EcWitnessBundle")]
pub fn load_data_add_legacy(
    network: &str,
) -> (
    usize,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<i64>,
) {
    std::env::set_var("VPIN_ALLOW_LEGACY_WITNESS", "1");
    load_data_add(network).expect("load_data_add_legacy")
}
