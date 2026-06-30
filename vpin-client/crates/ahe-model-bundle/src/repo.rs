use std::path::{Path, PathBuf};

/// Locate vPIN-main repo root (walk up from vpin-client/crates/*).
pub fn detect_repo_root() -> PathBuf {
    if let Ok(r) = std::env::var("VPIN_REPO_ROOT") {
        return PathBuf::from(r);
    }
    let mut dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    for _ in 0..8 {
        if dir.join("vpin-client").is_dir() && dir.join("model_training").is_dir() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

pub fn default_network_a_weights_dir(repo: &Path) -> PathBuf {
    repo.join("model_training/outputs/20260622_184254")
}

pub fn registry_weights_dir(repo: &Path, model_id: &str) -> Option<PathBuf> {
    let registry = repo.join("vpin-backend/data/models/registry.json");
    let raw = std::fs::read_to_string(registry).ok()?;
    let doc: serde_json::Value = serde_json::from_str(&raw).ok()?;
    // Registry is {"models": [...]}
    let entries = doc["models"].as_array()?;
    for entry in entries {
        if entry.get("id").and_then(|v| v.as_str()) == Some(model_id) {
            let rel = entry.get("weights_dir")?.as_str()?;
            let p = PathBuf::from(rel);
            return Some(if p.is_absolute() {
                p
            } else {
                repo.join(p)
            });
        }
    }
    None
}

/// Same as `registry_weights_dir` but also returns the model's `network` field.
pub fn registry_model_info(repo: &Path, model_id: &str) -> Option<(PathBuf, String)> {
    let registry = repo.join("vpin-backend/data/models/registry.json");
    let raw = std::fs::read_to_string(registry).ok()?;
    let doc: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let entries = doc["models"].as_array()?;
    for entry in entries {
        if entry.get("id").and_then(|v| v.as_str()) == Some(model_id) {
            let rel = entry.get("weights_dir")?.as_str()?;
            let p = PathBuf::from(rel);
            let dir = if p.is_absolute() { p } else { repo.join(p) };
            let network = entry
                .get("network")
                .and_then(|v| v.as_str())
                .unwrap_or("A")
                .to_string();
            return Some((dir, network));
        }
    }
    None
}
