//! Shared trace path resolution (run_dir or model_exports fallback).

use std::path::PathBuf;

pub fn trace_artifacts_dir(network: &str) -> PathBuf {
    if let Ok(root) = std::env::var("VPIN_TRACE_ROOT") {
        return PathBuf::from(root);
    }
    if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        return PathBuf::from(run).join("proof_artifacts");
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
}

pub fn trace_file(network: &str, name: &str) -> PathBuf {
    trace_artifacts_dir(network).join(name)
}
