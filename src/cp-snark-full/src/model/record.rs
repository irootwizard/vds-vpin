//! Per-model **storage record** (index metadata + commitment / truncation slots).
//!
//! Serialized as `record.json` beside `manifest.json` and `model_export.json`.
//! See `docs/task3-模型接入解析与存储方案.md`.

use serde::{Deserialize, Serialize};

use super::manifest::ModelSource;

/// Lifecycle of $\mathsf{cm}_{\mathbf{W}}$ on this record (task3(c) hooks [`crate::commit::commit_model`]).
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CommitmentStatus {
    #[default]
    /// Weights on disk; commitment not computed yet.
    Pending,
    /// `cm_weights` / digest filled (e.g. after server `setup_and_commit`).
    Committed,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ModelCommitmentSlot {
    pub status: CommitmentStatus,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cm_weights_point_hex: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub digest_hex: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub committed_at_utc: Option<String>,
    /// Future: Pedersen blind $r$ or Merkle root (not in protocol.json today).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blind_hex: Option<String>,
}

/// One planned client truncation round (task3 §2b); filled by offline planner later.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TruncateCheckpoint {
    /// 0-based layer index in [`crate::statement::NetworkTopology`].
    pub layer_index: u8,
    /// e.g. `after_relu_fc0`, `after_conv`.
    pub trigger: String,
    /// Recommended output bit budget after client TReLU/shift.
    pub bits_budget: u16,
    #[serde(default)]
    pub note: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TruncationPlanStatus {
    /// Placeholder until task3 §3.1 algorithm writes checkpoints.
    Stub,
    Ready,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TruncationPlanSlot {
    pub status: TruncationPlanStatus,
    pub plan_version: u32,
    #[serde(default)]
    pub checkpoints: Vec<TruncateCheckpoint>,
}

impl Default for TruncationPlanSlot {
    fn default() -> Self {
        Self {
            status: TruncationPlanStatus::Stub,
            plan_version: 0,
            checkpoints: vec![],
        }
    }
}

/// Full storage row for one registered model (DB row / `record.json`).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelRecord {
    pub model_id: String,
    #[serde(default)]
    pub display_name: String,
    /// ISO-8601 UTC, e.g. `2026-06-04T08:00:00Z`.
    pub created_at_utc: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at_utc: Option<String>,
    /// Logical vPIN network folder for EC trace (`A`…`E`) and built-in pool tables.
    pub topology_network: String,
    /// Relative to the model directory (e.g. `manifest.json`).
    pub manifest_path: String,
    /// Relative weights export (e.g. `model_export.json`).
    pub weights_path: String,
    pub source: ModelSource,
    #[serde(default)]
    pub commitment: ModelCommitmentSlot,
    #[serde(default)]
    pub truncation_plan: TruncationPlanSlot,
    /// Optional SHA-256 over canonical `model_export.json` bytes (client pin).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub weights_digest_hex: Option<String>,
}

/// Entry in `model_store/index.json`.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelIndexEntry {
    pub model_id: String,
    /// Path relative to store root, e.g. `models/vpin-network-a/record.json`.
    pub record_path: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelStoreIndex {
    pub version: u32,
    pub models: Vec<ModelIndexEntry>,
}

impl ModelRecord {
    pub fn vpin_network_a_sample() -> Self {
        Self {
            model_id: "vpin-network-a".into(),
            display_name: "vPIN Network A (demo)".into(),
            created_at_utc: "2026-06-04T00:00:00Z".into(),
            updated_at_utc: None,
            topology_network: "A".into(),
            manifest_path: "manifest.json".into(),
            weights_path: "model_export.json".into(),
            source: ModelSource::VpinNpy { version: 1 },
            commitment: ModelCommitmentSlot {
                status: CommitmentStatus::Pending,
                ..Default::default()
            },
            truncation_plan: TruncationPlanSlot::default(),
            weights_digest_hex: None,
        }
    }
}
