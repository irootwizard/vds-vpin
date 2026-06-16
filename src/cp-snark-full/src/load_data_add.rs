use serde_json::Value;
use std::{fs::File, io::Read};

fn rust_files_base() -> String {
    format!(
        "{}/../proof_generation/vPIN_proof_generation/src/rust_files",
        env!("CARGO_MANIFEST_DIR")
    )
}

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
    let base = rust_files_base();
    let file1_path_str = format!("{base}/{network}/pointAdd/point_add_px_byte.json");
    let file2_path_str = format!("{base}/{network}/pointAdd/point_add_py_byte.json");
    let file3_path_str = format!("{base}/{network}/pointAdd/point_add_rx_byte.json");
    let file4_path_str = format!("{base}/{network}/pointAdd/point_add_ry_byte.json");
    let file5_path_str = format!("{base}/{network}/pointAdd/point_add_rz_byte.json");

    let read_matrix = |path: &str| -> Vec<Vec<i64>> {
        let mut file = File::open(path).expect("Failed to open json");
        let mut contents = String::new();
        file.read_to_string(&mut contents).expect("Failed to read file");
        let parsed: Vec<Vec<Value>> = serde_json::from_str(&contents).expect("Failed to parse JSON");
        parsed
            .into_iter()
            .map(|row| row.into_iter().filter_map(|v| v.as_i64()).collect())
            .collect()
    };

    let point_add_px_byte = read_matrix(&file1_path_str);
    let len = point_add_px_byte.len();
    let point_add_py_byte = read_matrix(&file2_path_str);
    let point_add_rx_byte = read_matrix(&file3_path_str);
    let point_add_ry_byte = read_matrix(&file4_path_str);

    let mut file5 = File::open(&file5_path_str).expect("Failed to open rz json");
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
