//! R4 cross-process helpers: client challenge JSON, artifact verify by path.

use std::fs;
use std::path::Path;

use crate::challenge::ClientChallenge;
use crate::load_data;
use crate::load_data_add;
use crate::protocol::artifacts::ProtocolArtifacts;
use crate::prove::pipeline::prover_pipeline;
use crate::verify::pipeline::verifier_pipeline;

/// Client-side: sample challenge and return JSON for TLS transfer to prover.
pub fn sample_challenge_json(network: &str) -> Result<String, String> {
    let (num_mults, _, _, _, _) = load_data::load_data(network).map_err(|e| e.to_string())?;
    let (num_adds, _, _, _, _, _) = load_data_add::load_data_add(network).map_err(|e| e.to_string())?;
    let challenge = ClientChallenge::sample(num_adds, num_mults);
    serde_json::to_string_pretty(&challenge).map_err(|e| e.to_string())
}

pub fn challenge_from_json(json: &str) -> Result<ClientChallenge, String> {
    serde_json::from_str(json).map_err(|e| format!("challenge json: {e}"))
}

/// Server: prove with client-supplied challenge (not locally sampled).
pub fn prover_with_challenge_json(
    network: &str,
    challenge_json: &str,
) -> Result<ProtocolArtifacts, String> {
    let challenge = challenge_from_json(challenge_json)?;
    prover_pipeline(network, challenge).map_err(|e| format!("{e:?}"))
}

/// Client: verify artifacts file (uses openings — no `weight.json`).
pub fn verifier_from_path(path: &Path) -> Result<(), String> {
    let json = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let artifacts: ProtocolArtifacts =
        serde_json::from_str(&json).map_err(|e| format!("artifacts json: {e}"))?;
    if artifacts.model_opening.is_none() {
        return Err(
            "artifacts missing model_opening — regenerate proof with W* commitment pipeline"
                .into(),
        );
    }
    verifier_pipeline(&artifacts)
}
