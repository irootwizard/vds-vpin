//! M4: EC witness sliced by layer manifest (`pointMult/manifest.json`).

use std::fs::File;
use std::io::Read;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use super::ec::EcTrace;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EcLayerRange {
    pub kind: String,
    pub index: u8,
    pub pt_mul_start: usize,
    pub pt_mul_end: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EcLayerManifest {
    pub network: String,
    pub num_pt_mul: usize,
    pub num_pt_add: usize,
    pub layers: Vec<EcLayerRange>,
}

#[derive(Clone, Debug)]
pub struct EcLayerSlice {
    pub range: EcLayerRange,
    pub weights: Vec<u128>,
}

pub fn manifest_path(network: &str) -> PathBuf {
    super::ec::ec_trace_dir(network)
        .join("pointMult")
        .join("manifest.json")
}

pub fn load_ec_manifest(network: &str) -> std::io::Result<EcLayerManifest> {
    let path = manifest_path(network);
    let mut file = File::open(path)?;
    let mut raw = String::new();
    file.read_to_string(&mut raw)?;
    serde_json::from_str(&raw).map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))
}

pub fn slice_ec_by_layer(trace: &EcTrace, manifest: &EcLayerManifest) -> Vec<EcLayerSlice> {
    manifest
        .layers
        .iter()
        .map(|range| {
            let start = range.pt_mul_start.min(trace.pt_mul_weights.len());
            let end = range.pt_mul_end.min(trace.pt_mul_weights.len());
            EcLayerSlice {
                range: range.clone(),
                weights: trace.pt_mul_weights[start..end].to_vec(),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_manifest_a_if_present() {
        let path = manifest_path("A");
        if path.is_file() {
            let m = load_ec_manifest("A").unwrap();
            assert_eq!(m.network, "A");
        }
    }
}
