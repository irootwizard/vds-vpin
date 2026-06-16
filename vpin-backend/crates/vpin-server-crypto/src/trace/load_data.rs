use serde_json::Value;
use std::path::PathBuf;
use std::{fs::File, io::Read, str::FromStr};

pub fn rust_files_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../src/proof_generation/vPIN_proof_generation/src/rust_files")
        .canonicalize()
        .unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(
                "../../../src/proof_generation/vPIN_proof_generation/src/rust_files",
            )
        })
}

pub fn witness_available(network: &str) -> bool {
    rust_files_root()
        .join(network)
        .join("pointMult")
        .join("weight.json")
        .is_file()
}

pub fn load_data(network: &str) -> (usize, Vec<u128>, Vec<Vec<i64>>, Vec<Vec<i64>>, usize) {
    let base = rust_files_root().join(network).join("pointMult");
    let file1_path = base.join("weight.json");
    let file2_path = base.join("point_mult_px_byte.json");
    let file3_path = base.join("point_mult_py_byte.json");

    let mut file = File::open(&file1_path).expect("Failed to open weight.json");
    let mut contents = String::new();
    file.read_to_string(&mut contents).expect("Failed to read file");

    let parsed: Vec<String> = serde_json::from_str(&contents).expect("Failed to parse JSON");
    let weights: Vec<u128> = parsed
        .into_iter()
        .map(|weight_str| u128::from_str(weight_str.as_str()).expect("Failed to parse weight"))
        .collect();
    let weights_len = weights.len();

    let mut file2 = File::open(&file2_path).expect("Failed to open point_mult_px_byte.json");
    let mut contents2 = String::new();
    file2
        .read_to_string(&mut contents2)
        .expect("Failed to read file");
    let parsed2: Vec<Vec<Value>> =
        serde_json::from_str(&contents2).expect("Failed to parse JSON");
    let point_mult_px_byte: Vec<Vec<i64>> = parsed2
        .into_iter()
        .map(|row| row.into_iter().filter_map(|v| v.as_i64()).collect())
        .collect();

    let mut file3 = File::open(&file3_path).expect("Failed to open point_mult_py_byte.json");
    let mut contents3 = String::new();
    file3
        .read_to_string(&mut contents3)
        .expect("Failed to read file");
    let parsed3: Vec<Vec<Value>> =
        serde_json::from_str(&contents3).expect("Failed to parse JSON");
    let point_mult_py_byte: Vec<Vec<i64>> = parsed3
        .into_iter()
        .map(|row| row.into_iter().filter_map(|v| v.as_i64()).collect())
        .collect();

    let n_bit = 128usize;
    (weights_len, weights, point_mult_px_byte, point_mult_py_byte, n_bit)
}

pub fn load_weights_only(network: &str) -> Vec<u128> {
    let (_, weights, _, _, _) = load_data(network);
    weights
}

#[allow(dead_code)]
pub fn ec_witness_root(network: &str) -> PathBuf {
    rust_files_root().join(network)
}
