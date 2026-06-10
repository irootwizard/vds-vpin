use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

use crate::challenge::ClientChallenge;
use crate::commit::{
    InputCommitmentBundle, InputCommitmentOpening, ModelCommitmentBundle, ModelCommitmentOpening,
};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SubCircuitProof {
    pub circuit_name: String,
    pub proof_bytes: Vec<u8>,
    pub public_inputs_hex: Vec<String>,
    pub comm_para_hex: Vec<String>,
    pub comm_input_hex: Vec<String>,
    pub num_cons: usize,
    pub num_vars: usize,
    pub num_inputs: usize,
    pub num_non_zero: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct EcProofBundle {
    pub point_add: Option<SubCircuitProof>,
    pub point_mult: Option<SubCircuitProof>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProveTiming {
    pub check_scalar_ms: u128,
    pub prove_mac_ms: u128,
    pub prove_ec_ms: u128,
    pub total_ms: u128,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProtocolArtifacts {
    #[serde(default = "default_version")]
    pub version: u32,
    pub network: String,
    pub model_commitment: ModelCommitmentBundle,
    pub input_commitment: InputCommitmentBundle,
    #[serde(default)]
    pub model_opening: Option<ModelCommitmentOpening>,
    #[serde(default)]
    pub input_opening: Option<InputCommitmentOpening>,
    pub client_challenge: ClientChallenge,
    #[serde(default)]
    pub ec_proof: Option<EcProofBundle>,
    #[serde(default)]
    pub point_add_proof: Option<SubCircuitProof>,
    #[serde(default)]
    pub point_mult_proof: Option<SubCircuitProof>,
    pub rlc_binding_hex: String,
    pub proof_coverage: String,
    #[serde(default)]
    pub prove_timing: Option<ProveTiming>,
    pub prove_time_ms: u128,
    pub verify_time_ms: u128,
}

fn default_version() -> u32 {
    2
}

pub fn artifacts_dir(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("artifacts")
        .join(network)
}

pub fn save_artifacts(artifacts: &ProtocolArtifacts) -> std::io::Result<PathBuf> {
    let dir = artifacts_dir(&artifacts.network);
    fs::create_dir_all(&dir)?;
    let path = dir.join("protocol.json");
    let json = serde_json::to_string_pretty(artifacts).expect("serialize artifacts");
    fs::write(&path, json)?;
    Ok(path)
}

pub fn load_artifacts(path: &Path) -> std::io::Result<ProtocolArtifacts> {
    let raw = fs::read_to_string(path)?;
    serde_json::from_str(&raw).map_err(|e| {
        std::io::Error::new(std::io::ErrorKind::InvalidData, e)
    })
}
