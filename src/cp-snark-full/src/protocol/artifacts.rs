use libspartan::scalar::Scalar;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

use crate::challenge::ClientChallenge;
use crate::circuit::ec::SubCircuitProof;
use crate::circuit::mac_rlc::MacRlcProof;
use crate::commit::{
    InputCommitmentBundle, InputCommitmentOpening, ModelCommitmentBundle, ModelCommitmentOpening,
};
use crate::prove::ec::EcProofBundle;
use crate::protocol::coverage::ProofCoverageV2;
use crate::statement::NetworkTopology;

fn default_version() -> u32 {
    1
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProveTiming {
    pub check_scalar_ms: u128,
    pub prove_mac_ms: u128,
    pub prove_ec_ms: u128,
    pub total_ms: u128,
}

/// Protocol bundle (v1 flat + v2 fields). Old `protocol.json` without `version` deserializes as v1.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProtocolArtifacts {
    #[serde(default = "default_version")]
    pub version: u32,
    pub network: String,
    #[serde(default)]
    pub topology: Option<NetworkTopology>,
    pub model_commitment: ModelCommitmentBundle,
    pub input_commitment: InputCommitmentBundle,
    /// Plaintext Pedersen opening for $\mathsf{cm}_W$ (cross-process verify).
    #[serde(default)]
    pub model_opening: Option<ModelCommitmentOpening>,
    /// Plaintext Pedersen opening for $\mathsf{cm}_x$.
    #[serde(default)]
    pub input_opening: Option<InputCommitmentOpening>,
    pub client_challenge: ClientChallenge,
    /// L1 binding check passed (witness slots match opened weights).
    #[serde(default)]
    pub l1_binding_ok: Option<bool>,
    /// Merkle root over full $\mathbf{W}^*$ leaves (L1′).
    #[serde(default)]
    pub w_star_merkle_root_hex: Option<String>,
    /// SHA256 digest of client input binding scalars (when present).
    #[serde(default)]
    pub input_binding_len: Option<usize>,
    /// v2 EC proof family.
    #[serde(default)]
    pub ec_proof: Option<EcProofBundle>,
    /// v1 fields (kept for backward compatibility).
    #[serde(default)]
    pub point_add_proof: Option<SubCircuitProof>,
    #[serde(default)]
    pub point_mult_proof: Option<SubCircuitProof>,
    #[serde(default)]
    pub mac_proof: Option<MacRlcProof>,
    pub rlc_binding_hex: String,
    #[serde(default = "default_proof_coverage_str")]
    pub proof_coverage: String,
    #[serde(default)]
    pub scalar_check_ok: Option<bool>,
    #[serde(default)]
    pub prove_timing: Option<ProveTiming>,
    pub prove_time_ms: u128,
    pub verify_time_ms: u128,
}

fn default_proof_coverage_str() -> String {
    ProofCoverageV2::EcOnly.as_str().to_string()
}

impl ProtocolArtifacts {
    /// Normalize v1 → v2 ec_proof view.
    pub fn ec_proof_view(&self) -> EcProofBundle {
        if let Some(ref ec) = self.ec_proof {
            return ec.clone();
        }
        EcProofBundle {
            point_add: self.point_add_proof.clone(),
            point_mult: self.point_mult_proof.clone(),
        }
    }

    pub fn sync_v1_ec_fields(&mut self) {
        let ec = self.ec_proof_view();
        self.point_add_proof = ec.point_add;
        self.point_mult_proof = ec.point_mult;
        if self.ec_proof.is_none() {
            self.ec_proof = Some(EcProofBundle {
                point_add: self.point_add_proof.clone(),
                point_mult: self.point_mult_proof.clone(),
            });
        }
    }

    pub fn coverage_v2(&self) -> ProofCoverageV2 {
        match self.proof_coverage.as_str() {
            "ec_plus_scalar_check" | "conv_rlc" | "pool_add" | "fc_rlc" => {
                ProofCoverageV2::EcPlusScalarCheck
            }
            "ec_plus_mac_rlc" | "server_linear_layers" => ProofCoverageV2::EcPlusMacRlc,
            "ec_plus_l1_binding" => ProofCoverageV2::EcPlusL1Binding,
            _ => ProofCoverageV2::EcOnly,
        }
    }
}

pub fn artifacts_dir(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("artifacts")
        .join(network)
}

pub fn artifact_path(network: &str) -> PathBuf {
    artifacts_dir(network).join("protocol.json")
}

pub fn save_artifacts(artifacts: &ProtocolArtifacts) -> std::io::Result<()> {
    let mut art = artifacts.clone();
    art.sync_v1_ec_fields();
    let dir = artifacts_dir(&art.network);
    fs::create_dir_all(&dir)?;
    let json = serde_json::to_string_pretty(&art).expect("serialize artifacts");
    fs::write(artifact_path(&art.network), json)
}

pub fn load_artifacts(network: &str) -> std::io::Result<ProtocolArtifacts> {
    let json = fs::read_to_string(artifact_path(network))?;
    let mut art: ProtocolArtifacts = serde_json::from_str(&json).expect("deserialize artifacts");
    art.sync_v1_ec_fields();
    Ok(art)
}

#[derive(Debug, serde::Deserialize)]
struct InputBindingJson {
    network_id: String,
    input_flat: Vec<String>,
}

fn input_binding_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("input_binding.json")
}

/// Load client input scalars for $\mathsf{cm}_x$ (if `input_binding.json` exists).
pub fn load_input_binding(network: &str) -> Option<Vec<u128>> {
    let path = input_binding_path(network);
    let json = fs::read_to_string(&path).ok()?;
    let b: InputBindingJson = serde_json::from_str(&json).ok()?;
    if b.network_id != network {
        return None;
    }
    b.input_flat
        .iter()
        .map(|s| s.parse::<u128>().ok())
        .collect()
}

fn input_digest_scalar(input_flat: &[u128]) -> Scalar {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    for v in input_flat {
        h.update(v.to_le_bytes());
    }
    let d = h.finalize();
    let mut wide = [0u8; 64];
    wide[..32].copy_from_slice(&d);
    Scalar::from_bytes_wide(&wide)
}

/// Public inputs for sub-circuits: E₂ coefficient **a** + optional input digest.
pub fn public_inputs_for_network(network: &str) -> Vec<Scalar> {
    let curve = crate::curve::CurveE2Params::vpin_default();
    let a_scalar = crate::curve::embed_bigint_str_to_scalar(&curve.a);
    let mut out = vec![a_scalar];
    if let Some(inp) = load_input_binding(network) {
        out.push(input_digest_scalar(&inp));
    }
    out
}
