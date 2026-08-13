//! SHA-256 digest over MAC layer trace JSON (M1 binding).

use std::fs;
use std::path::Path;

use sha2::{Digest, Sha256};

use super::paths::trace_file;

const TRACE_FILES: &[&str] = &["conv_trace.json", "pool_trace.json", "fc_trace.json"];

/// Concatenate raw bytes of conv/pool/fc traces and return hex SHA-256.
pub fn scalar_trace_digest_hex(network: &str) -> Result<String, String> {
    let mut h = Sha256::new();
    for name in TRACE_FILES {
        let p = trace_file(network, name);
        if !p.is_file() {
            return Err(format!("trace file missing: {p:?}"));
        }
        let bytes = fs::read(&p).map_err(|e| format!("read {p:?}: {e}"))?;
        h.update(name.as_bytes());
        h.update(&bytes);
    }
    Ok(hex::encode(h.finalize()))
}

/// Same digest from an explicit proof_artifacts directory.
pub fn scalar_trace_digest_hex_from_dir(artifacts_dir: &Path) -> Result<String, String> {
    let mut h = Sha256::new();
    for name in TRACE_FILES {
        let p = artifacts_dir.join(name);
        if !p.is_file() {
            return Err(format!("trace file missing: {p:?}"));
        }
        let bytes = fs::read(&p).map_err(|e| format!("read {p:?}: {e}"))?;
        h.update(name.as_bytes());
        h.update(&bytes);
    }
    Ok(hex::encode(h.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn digest_standard_run_deterministic() {
        let run = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../model_training/outputs/20260622_184254/proof_artifacts");
        if !run.join("conv_trace.json").is_file() {
            return;
        }
        let d1 = scalar_trace_digest_hex_from_dir(&run).unwrap();
        let d2 = scalar_trace_digest_hex_from_dir(&run).unwrap();
        assert_eq!(d1, d2);
        assert_eq!(d1.len(), 64);
    }
}
