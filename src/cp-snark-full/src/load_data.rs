use serde_json::Value;
use std::{fs::File, io::Read, path::Path, str::FromStr};

fn rust_files_base() -> String {
    format!(
        "{}/../proof_generation/vPIN_proof_generation/src/rust_files",
        env!("CARGO_MANIFEST_DIR")
    )
}

pub fn load_data(network: &str) -> (usize, Vec<u128>, Vec<Vec<i64>>, Vec<Vec<i64>>, usize) {
    let base = rust_files_base();
    let file1_path_str = format!("{base}/{network}/pointMult/weight.json");
    let file2_path_str = format!("{base}/{network}/pointMult/point_mult_px_byte.json");
    let file3_path_str = format!("{base}/{network}/pointMult/point_mult_py_byte.json");

    let mut file = File::open(&file1_path_str).expect("Failed to open weight.json");
    let mut contents = String::new();
    file.read_to_string(&mut contents).expect("Failed to read file");

    let parsed: Vec<String> = serde_json::from_str(&contents).expect("Failed to parse JSON");
    let weights: Vec<u128> = parsed
        .into_iter()
        .map(|weight_str| u128::from_str(weight_str.as_str()).expect("Failed to parse weight"))
        .collect();
    let weights_len = weights.len();

    let mut file2 = File::open(&file2_path_str).expect("Failed to open point_mult_px_byte.json");
    let mut contents2 = String::new();
    file2
        .read_to_string(&mut contents2)
        .expect("Failed to read file");
    let parsed2: Vec<Vec<Value>> = serde_json::from_str(&contents2).expect("Failed to parse JSON");
    let mut point_mult_x_byte: Vec<Vec<i64>> = vec![];
    for row in parsed2 {
        let inner_row: Vec<i64> = row.into_iter().filter_map(|v| v.as_i64()).collect();
        point_mult_x_byte.push(inner_row);
    }

    let mut file3 = File::open(&file3_path_str).expect("Failed to open point_mult_py_byte.json");
    let mut contents3 = String::new();
    file3
        .read_to_string(&mut contents3)
        .expect("Failed to read file");
    let parsed3: Vec<Vec<Value>> = serde_json::from_str(&contents3).expect("Failed to parse JSON");
    let mut point_mult_y_byte: Vec<Vec<i64>> = vec![];
    for row2 in parsed3 {
        let inner_row2: Vec<i64> = row2.into_iter().filter_map(|v| v.as_i64()).collect();
        point_mult_y_byte.push(inner_row2);
    }

    (weights_len, weights, point_mult_x_byte, point_mult_y_byte, 128)
}

pub fn load_weights_only(network: &str) -> Vec<u128> {
    let (_, weights, _, _, _) = load_data(network);
    weights
}
