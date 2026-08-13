//! EC witness counts and per-layer j-intervals (from `ec_witness_schedule.json`).

use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Clone, Debug, Deserialize)]
pub struct EcWitnessLayerSchedule {
    pub layer_id: String,
    pub kind: String,
    pub pt_mul: usize,
    pub pt_add: usize,
    pub pt_mul_start: usize,
    pub pt_mul_end: usize,
    #[serde(default)]
    pub pt_add_start: usize,
    #[serde(default)]
    pub pt_add_end: usize,
}

#[derive(Clone, Debug, Deserialize)]
pub struct EcWitnessSchedule {
    pub network_id: String,
    #[serde(default)]
    pub mode: String,
    pub layers: Vec<EcWitnessLayerSchedule>,
    pub total_pt_mul: usize,
    pub total_pt_add: usize,
}

#[derive(Clone, Debug, Deserialize)]
struct ScheduleFileRoot {
    schedules: SchedulesMap,
}

#[derive(Clone, Debug, Deserialize)]
struct SchedulesMap {
    paper_proof: EcWitnessSchedule,
}

pub fn load_schedule_from_run_dir(run_dir: &Path, mode: &str) -> Result<EcWitnessSchedule, String> {
    let path = run_dir.join("proof_artifacts").join("ec_witness_schedule.json");
    load_schedule_file(&path, mode)
}

pub fn load_schedule_file(path: &Path, mode: &str) -> Result<EcWitnessSchedule, String> {
    let json = fs::read_to_string(path).map_err(|e| format!("{path:?}: {e}"))?;
    if mode == "paper_proof" {
        let root: ScheduleFileRoot =
            serde_json::from_str(&json).map_err(|e| format!("parse schedule: {e}"))?;
        Ok(root.schedules.paper_proof)
    } else {
        let sched: EcWitnessSchedule =
            serde_json::from_str(&json).map_err(|e| format!("parse schedule: {e}"))?;
        Ok(sched)
    }
}

impl EcWitnessSchedule {
    pub fn validate_counts(&self) -> Result<(), String> {
        let sum_mul: usize = self.layers.iter().map(|l| l.pt_mul).sum();
        let sum_add: usize = self.layers.iter().map(|l| l.pt_add).sum();
        if sum_mul != self.total_pt_mul {
            return Err(format!(
                "schedule pt_mul sum {sum_mul} != total {}",
                self.total_pt_mul
            ));
        }
        if sum_add != self.total_pt_add {
            return Err(format!(
                "schedule pt_add sum {sum_add} != total {}",
                self.total_pt_add
            ));
        }
        Ok(())
    }
}
