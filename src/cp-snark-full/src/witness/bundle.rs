//! Per-model-run EC witness bundle and proof plan handles.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

use super::schedule::{load_schedule_from_run_dir, EcWitnessSchedule};

static ACTIVE_ROOT: Mutex<Option<PathBuf>> = Mutex::new(None);

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EcWitnessManifestLayer {
    pub layer_id: String,
    pub kind: String,
    pub pt_mul_start: usize,
    pub pt_mul_end: usize,
    pub pt_add_start: usize,
    pub pt_add_end: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EcWitnessManifest {
    pub model_id: String,
    pub mode: String,
    pub total_pt_mul: usize,
    pub total_pt_add: usize,
    pub layers: Vec<EcWitnessManifestLayer>,
}

#[derive(Clone, Debug)]
pub struct EcWitnessBundle {
    pub model_id: String,
    pub run_dir: PathBuf,
    pub root: PathBuf,
    pub schedule: EcWitnessSchedule,
    pub manifest: Option<EcWitnessManifest>,
}

#[derive(Clone, Debug)]
pub struct ProofPlan {
    pub model_id: String,
    pub run_dir: PathBuf,
    pub witness: EcWitnessBundle,
    pub schedule_mode: String,
}

#[derive(Clone, Debug)]
pub struct ModelProofContext {
    pub model_id: String,
    pub run_dir: PathBuf,
    pub witness: EcWitnessBundle,
}

pub fn set_active_ec_witness_root(root: Option<PathBuf>) {
    *ACTIVE_ROOT.lock().unwrap() = root;
}

pub fn clear_active_ec_witness_root() {
    set_active_ec_witness_root(None);
}

pub fn active_ec_witness_root() -> Option<PathBuf> {
    if let Some(r) = ACTIVE_ROOT.lock().unwrap().clone() {
        return Some(r);
    }
    std::env::var("VPIN_EC_WITNESS_ROOT")
        .ok()
        .map(PathBuf::from)
}

pub fn resolve_ec_witness_root() -> Result<PathBuf, String> {
    active_ec_witness_root().ok_or_else(|| {
        "EC witness root not set: use set_active_ec_witness_root, VPIN_EC_WITNESS_ROOT, \
         or prover_pipeline_with_context"
            .into()
    })
}

pub fn load_ec_witness_from_run_dir(
    run_dir: &Path,
    model_id: &str,
    mode: &str,
) -> Result<EcWitnessBundle, String> {
    let schedule = load_schedule_from_run_dir(run_dir, mode)?;
    schedule.validate_counts()?;
    let root = run_dir.join("proof_artifacts").join("ec_witness");
    if !root.join("pointMult").join("weight.json").is_file() {
        return Err(format!(
            "missing EC witness at {:?}/pointMult/weight.json — run export_proof_artifacts",
            root
        ));
    }
    let manifest_path = root.join("manifest.json");
    let manifest = if manifest_path.is_file() {
        let json = fs::read_to_string(&manifest_path).map_err(|e| e.to_string())?;
        Some(serde_json::from_str(&json).map_err(|e| e.to_string())?)
    } else {
        None
    };
    Ok(EcWitnessBundle {
        model_id: model_id.to_string(),
        run_dir: run_dir.to_path_buf(),
        root,
        schedule,
        manifest,
    })
}

pub fn load_ec_witness(bundle_root: &Path, model_id: &str, schedule: EcWitnessSchedule) -> Result<EcWitnessBundle, String> {
    schedule.validate_counts()?;
    if !bundle_root.join("pointMult").join("weight.json").is_file() {
        return Err(format!(
            "missing {:?}/pointMult/weight.json",
            bundle_root
        ));
    }
    let run_dir = bundle_root
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| bundle_root.to_path_buf());
    let manifest_path = bundle_root.join("manifest.json");
    let manifest = if manifest_path.is_file() {
        let json = fs::read_to_string(&manifest_path).map_err(|e| e.to_string())?;
        Some(serde_json::from_str(&json).map_err(|e| e.to_string())?)
    } else {
        None
    };
    Ok(EcWitnessBundle {
        model_id: model_id.to_string(),
        run_dir,
        root: bundle_root.to_path_buf(),
        schedule,
        manifest,
    })
}

pub fn discover_run_bundle(model_id: &str, mode: &str) -> Result<EcWitnessBundle, String> {
    if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        return load_ec_witness_from_run_dir(Path::new(&run), model_id, mode);
    }
    Err("VPIN_RUN_DIR not set and no explicit run_dir".into())
}

impl ProofPlan {
    pub fn from_run_dir(run_dir: &Path, model_id: &str, mode: &str) -> Result<Self, String> {
        let witness = load_ec_witness_from_run_dir(run_dir, model_id, mode)?;
        Ok(Self {
            model_id: model_id.to_string(),
            run_dir: run_dir.to_path_buf(),
            witness: witness.clone(),
            schedule_mode: mode.to_string(),
        })
    }

    pub fn activate_witness(&self) {
        set_active_ec_witness_root(Some(self.witness.root.clone()));
    }
}

impl ModelProofContext {
    pub fn from_plan(plan: &ProofPlan) -> Self {
        Self {
            model_id: plan.model_id.clone(),
            run_dir: plan.run_dir.clone(),
            witness: plan.witness.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schedule_validation_network_a_fixture() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../model_training/outputs/20260622_184254");
        if !repo.is_dir() {
            return;
        }
        let sched = load_schedule_from_run_dir(&repo, "paper_proof").unwrap();
        assert_eq!(sched.total_pt_mul, 178);
        assert_eq!(sched.total_pt_add, 2144);
        sched.validate_counts().unwrap();
    }
}
