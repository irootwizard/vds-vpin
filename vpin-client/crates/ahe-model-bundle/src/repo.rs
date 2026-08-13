use std::path::{Path, PathBuf};

/// Locate vPIN-main repo root (walk up from vpin-client/crates/*) or release bundle root.
pub fn detect_repo_root() -> PathBuf {
    if let Ok(r) = std::env::var("VPIN_REPO_ROOT") {
        return PathBuf::from(r);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if dir.join("data").join("bsgs").join("table.bin").is_file() {
                return dir.to_path_buf();
            }
        }
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
    let release = repo.join("data/weights/cnn-mnist-trained");
    if release.is_dir() {
        return release;
    }
    repo.join("model_training/outputs/20260622_184254")
}

fn registry_candidates(repo: &Path) -> [PathBuf; 2] {
    [
        repo.join("config/models-registry.json"),
        repo.join("vpin-backend/data/models/registry.json"),
    ]
}

pub fn registry_weights_dir(repo: &Path, model_id: &str) -> Option<PathBuf> {
    for registry in registry_candidates(repo) {
        let raw = std::fs::read_to_string(&registry).ok()?;
        let doc: serde_json::Value = serde_json::from_str(&raw).ok()?;
        let entries = doc
            .get("models")
            .and_then(|v| v.as_array())
            .or_else(|| doc.as_array())?;
        for entry in entries {
            if entry.get("id").and_then(|v| v.as_str()) == Some(model_id) {
                let rel = entry.get("weights_dir")?.as_str()?;
                let p = PathBuf::from(rel);
                return Some(if p.is_absolute() { p } else { repo.join(p) });
            }
        }
    }
    None
}
