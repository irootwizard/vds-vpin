//! Where **W** comes from: vPIN `.npy` tree, exported JSON, or (future) Hugging Face.

use serde::{Deserialize, Serialize};

/// Provenance of model weights (for client HF download + digest pin, etc.).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ModelSource {
    /// Current repo: `cnn_networks/Pre_trained_model/*.npy` + inline conv in Server.py.
    VpinNpy { version: u8 },
    /// Flattened tensors exported for Rust (`model_export.json`).
    ExportedJson { path: String },
    /// Client/server both pull same revision; digest checked before `ModelParams` fill.
    HuggingFace {
        repo_id: String,
        revision: String,
        weights_digest_hex: String,
        export_manifest_path: Option<String>,
    },
}

/// Layout metadata for `VpinNpy` (which files map to which layer).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct VpinNpyLayout {
    pub version: u8,
    pub network_folder: String,
    pub conv_filter_inline: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelManifest {
    pub model_id: String,
    pub source: ModelSource,
    #[serde(default)]
    pub topology_hash_hex: Option<String>,
    #[serde(default)]
    pub vpin_layout: Option<VpinNpyLayout>,
}

impl ModelManifest {
    pub fn vpin_version(version: u8, network_folder: &str) -> Self {
        Self {
            model_id: format!("vpin-v{version}"),
            source: ModelSource::VpinNpy { version },
            topology_hash_hex: None,
            vpin_layout: Some(VpinNpyLayout {
                version,
                network_folder: network_folder.to_string(),
                conv_filter_inline: true,
            }),
        }
    }
}
