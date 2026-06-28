//! EC gadget witness from existing `rust_files/{network}/pointAdd|pointMult` JSON.

use std::fs::File;
use std::io::Read;
use std::path::PathBuf;
use std::str::FromStr;

#[derive(Clone, Debug, Default)]
pub struct EcTrace {
    pub network: String,
    pub pt_mul_weights: Vec<u128>,
    pub pt_mul_px: Vec<Vec<i64>>,
    pub pt_mul_py: Vec<Vec<i64>>,
    pub num_pt_adds: usize,
    pub num_pt_muls: usize,
    /// Scalar-mult gadget bit width from `load_data` (128).
    pub scalar_mul_bits: usize,
}

fn rust_files_base() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../proof_generation/vPIN_proof_generation/src/rust_files")
}

pub fn ec_trace_dir(network: &str) -> PathBuf {
    rust_files_base().join(network)
}

pub fn load_ec_trace(network: &str) -> std::io::Result<EcTrace> {
    let (num_mults, weights, px, py, bits) = crate::load_data::load_data(network)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    let (num_adds, _, _, _, _, _) = crate::load_data_add::load_data_add(network)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    Ok(EcTrace {
        network: network.to_string(),
        pt_mul_weights: weights,
        pt_mul_px: px,
        pt_mul_py: py,
        num_pt_adds: num_adds,
        num_pt_muls: num_mults,
        scalar_mul_bits: bits,
    })
}

/// Load weights only (alias for commitment path).
pub fn load_pt_mul_weights(network: &str) -> std::io::Result<Vec<u128>> {
    let base = rust_files_base();
    let path = base.join(network).join("pointMult/weight.json");
    let mut file = File::open(path)?;
    let mut contents = String::new();
    file.read_to_string(&mut contents)?;
    let parsed: Vec<String> = serde_json::from_str(&contents)?;
    Ok(parsed
        .into_iter()
        .map(|s| u128::from_str(&s).expect("weight parse"))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_ec_trace_a_if_present() {
        let legacy = ec_trace_dir("A").join("pointMult/weight.json");
        if !legacy.exists() {
            return;
        }
        std::env::set_var("VPIN_ALLOW_LEGACY_WITNESS", "1");
        let t = load_ec_trace("A").unwrap();
        assert_eq!(t.pt_mul_weights.len(), 178);
    }
}
