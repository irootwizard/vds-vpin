//! Model **registry + blob paths** — JSON file backend now; DB / HTTPS ingest later.
//!
//! Layout: `{store_root}/index.json`, `{store_root}/models/{id}/record.json`, …

use std::fs;
use std::path::{Path, PathBuf};

use super::load::{load_from_export_path, load_model_params, ModelLoadError};
use super::manifest::ModelManifest;
use super::params::ModelParams;
use super::record::{ModelIndexEntry, ModelRecord, ModelStoreIndex};

#[derive(Clone, Debug)]
pub enum StoreError {
    NotFound(String),
    Io(String),
    Parse(String),
    InvalidPath(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for StoreError {}

/// Storage backend for task3(a): index + per-model directory.
pub trait ModelStore: Send + Sync {
    fn root(&self) -> &Path;

    fn list_index(&self) -> Result<ModelStoreIndex, StoreError>;

    fn get_record(&self, model_id: &str) -> Result<ModelRecord, StoreError>;

    /// Resolve `weights_path` under the model dir and parse [`ModelParams`].
    fn load_params(&self, model_id: &str) -> Result<ModelParams, ModelLoadError>;

    /// Load manifest JSON from the model directory.
    fn load_manifest(&self, model_id: &str) -> Result<ModelManifest, StoreError>;

    /// Persist or update `record.json` (index must already list the model, or call [`register`].
    fn save_record(&self, record: &ModelRecord) -> Result<(), StoreError>;

    /// Append index entry + write `record.json` (does not copy weights).
    fn register(&self, record: &ModelRecord) -> Result<(), StoreError>;
}

/// Default on-disk store: `cp-snark-full/model_store/`.
#[derive(Clone, Debug)]
pub struct JsonFileModelStore {
    root: PathBuf,
}

impl JsonFileModelStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn default_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("model_store")
    }

    pub fn open_default() -> Self {
        Self::new(Self::default_root())
    }

    fn index_path(&self) -> PathBuf {
        self.root.join("index.json")
    }

    fn model_dir(&self, model_id: &str) -> PathBuf {
        self.root.join("models").join(model_id)
    }

    fn resolve_record_path(&self, entry: &ModelIndexEntry) -> PathBuf {
        self.root.join(&entry.record_path)
    }

    fn record_from_entry(&self, entry: &ModelIndexEntry) -> Result<ModelRecord, StoreError> {
        let path = self.resolve_record_path(entry);
        let json = fs::read_to_string(&path).map_err(|e| StoreError::Io(e.to_string()))?;
        serde_json::from_str(&json).map_err(|e| StoreError::Parse(e.to_string()))
    }

    pub fn model_dir_for(&self, model_id: &str) -> PathBuf {
        self.model_dir(model_id)
    }

    pub fn resolve_weights_path(&self, record: &ModelRecord) -> PathBuf {
        self.model_dir(&record.model_id).join(&record.weights_path)
    }

    pub fn resolve_manifest_path(&self, record: &ModelRecord) -> PathBuf {
        self.model_dir(&record.model_id).join(&record.manifest_path)
    }
}

impl ModelStore for JsonFileModelStore {
    fn root(&self) -> &Path {
        &self.root
    }

    fn list_index(&self) -> Result<ModelStoreIndex, StoreError> {
        let path = self.index_path();
        if !path.is_file() {
            return Ok(ModelStoreIndex {
                version: 1,
                models: vec![],
            });
        }
        let json = fs::read_to_string(&path).map_err(|e| StoreError::Io(e.to_string()))?;
        serde_json::from_str(&json).map_err(|e| StoreError::Parse(e.to_string()))
    }

    fn get_record(&self, model_id: &str) -> Result<ModelRecord, StoreError> {
        let index = self.list_index()?;
        let entry = index
            .models
            .iter()
            .find(|e| e.model_id == model_id)
            .ok_or_else(|| StoreError::NotFound(model_id.to_string()))?;
        self.record_from_entry(entry)
    }

    fn load_params(&self, model_id: &str) -> Result<ModelParams, ModelLoadError> {
        let record = self
            .get_record(model_id)
            .map_err(|e| ModelLoadError::Io(e.to_string()))?;
        let weights = self.resolve_weights_path(&record);
        if weights.is_file() {
            return load_from_export_path(&weights);
        }
        load_model_params(&record.topology_network)
    }

    fn load_manifest(&self, model_id: &str) -> Result<ModelManifest, StoreError> {
        let record = self.get_record(model_id)?;
        let path = self.resolve_manifest_path(&record);
        let json = fs::read_to_string(&path).map_err(|e| StoreError::Io(e.to_string()))?;
        serde_json::from_str(&json).map_err(|e| StoreError::Parse(e.to_string()))
    }

    fn save_record(&self, record: &ModelRecord) -> Result<(), StoreError> {
        let dir = self.model_dir(&record.model_id);
        fs::create_dir_all(&dir).map_err(|e| StoreError::Io(e.to_string()))?;
        let path = dir.join("record.json");
        let json = serde_json::to_string_pretty(record)
            .map_err(|e| StoreError::Parse(e.to_string()))?;
        fs::write(&path, json).map_err(|e| StoreError::Io(e.to_string()))
    }

    fn register(&self, record: &ModelRecord) -> Result<(), StoreError> {
        let mut index = self.list_index()?;
        if index.models.iter().any(|e| e.model_id == record.model_id) {
            return Err(StoreError::InvalidPath(format!(
                "model_id already registered: {}",
                record.model_id
            )));
        }
        let record_rel = format!("models/{}/record.json", record.model_id);
        index.models.push(ModelIndexEntry {
            model_id: record.model_id.clone(),
            record_path: record_rel,
        });
        fs::create_dir_all(self.root.join("models").join(&record.model_id))
            .map_err(|e| StoreError::Io(e.to_string()))?;
        self.save_record(record)?;
        let index_json = serde_json::to_string_pretty(&index)
            .map_err(|e| StoreError::Parse(e.to_string()))?;
        fs::create_dir_all(&self.root).map_err(|e| StoreError::Io(e.to_string()))?;
        fs::write(self.index_path(), index_json).map_err(|e| StoreError::Io(e.to_string()))
    }
}

/// After [`crate::commit::commit_model`], attach commitment fields to the stored record.
pub fn attach_commitment_to_record(
    record: &mut ModelRecord,
    point_hex: &str,
    digest_hex: &str,
    committed_at_utc: &str,
) {
    use super::record::CommitmentStatus;
    record.commitment.status = CommitmentStatus::Committed;
    record.commitment.cm_weights_point_hex = Some(point_hex.to_string());
    record.commitment.digest_hex = Some(digest_hex.to_string());
    record.commitment.committed_at_utc = Some(committed_at_utc.to_string());
    record.updated_at_utc = Some(committed_at_utc.to_string());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_store_lists_vpin_network_a() {
        let store = JsonFileModelStore::open_default();
        let index = store.list_index().expect("index");
        assert!(
            index.models.iter().any(|e| e.model_id == "vpin-network-a"),
            "seed index should contain vpin-network-a"
        );
        let p = store.load_params("vpin-network-a").expect("params");
        assert_eq!(p.network_id, "A");
        assert_eq!(p.conv.filter_flat.len(), 9);
    }
}
