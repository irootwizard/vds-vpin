use serde_json::Value;
use std::fs::File;
use std::io::Read;

use super::load_data::rust_files_root;

pub fn load_data_add(
    network: &str,
) -> (
    usize,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<Vec<i64>>,
    Vec<i64>,
) {
    let base = rust_files_root().join(network).join("pointAdd");

    let read_matrix = |path: &std::path::Path| -> Vec<Vec<i64>> {
        let mut file = File::open(path).expect("Failed to open json");
        let mut contents = String::new();
        file.read_to_string(&mut contents).expect("Failed to read file");
        let parsed: Vec<Vec<Value>> = serde_json::from_str(&contents).expect("Failed to parse JSON");
        parsed
            .into_iter()
            .map(|row| row.into_iter().filter_map(|v| v.as_i64()).collect())
            .collect()
    };

    let point_add_px_byte = read_matrix(&base.join("point_add_px_byte.json"));
    let len = point_add_px_byte.len();
    let point_add_py_byte = read_matrix(&base.join("point_add_py_byte.json"));
    let point_add_rx_byte = read_matrix(&base.join("point_add_rx_byte.json"));
    let point_add_ry_byte = read_matrix(&base.join("point_add_ry_byte.json"));

    let mut file5 = File::open(base.join("point_add_rz_byte.json")).expect("Failed to open rz json");
    let mut contents5 = String::new();
    file5
        .read_to_string(&mut contents5)
        .expect("Failed to read file");
    let parsed5: Vec<Value> = serde_json::from_str(&contents5).expect("Failed to parse JSON");
    let point_add_rz_byte: Vec<i64> = parsed5.into_iter().filter_map(|v| v.as_i64()).collect();

    (
        len,
        point_add_px_byte,
        point_add_py_byte,
        point_add_rx_byte,
        point_add_ry_byte,
        point_add_rz_byte,
    )
}
