use std::time::SystemTime;

use libspartan::scalar::Scalar;

use crate::challenge::rlc_bind_scalars;
use crate::commit::{
    opening_public_scalars, opening_weights_to_scalars, verify_input_commitment,
    verify_model_commitment, verify_pedersen_open_input, verify_pedersen_open_model,
};
use crate::curve::embed_u128_to_scalar;
use crate::protocol::artifacts::{public_inputs_for_network, ProtocolArtifacts};
use crate::circuit::bind_l1::{check_l1_ptmul_bindings, merkle_root_w_star};
use crate::model::load_w_star;
use crate::verify::ec::verify_ec_bundle;
use crate::verify::mac::verify_mac_rlc;

/// Resolve weight scalars for verify: prefer artifact opening (R4), else legacy `weight.json`.
fn resolve_weight_scalars(artifacts: &ProtocolArtifacts) -> Result<Vec<Scalar>, String> {
    if let Some(ref opening) = artifacts.model_opening {
        if !verify_pedersen_open_model(&artifacts.model_commitment, opening) {
            return Err("model Pedersen opening failed".into());
        }
        return opening_weights_to_scalars(opening);
    }
    // Legacy path (deprecated): local prover-side weight.json
    let weights = crate::load_data::load_weights_only(&artifacts.network);
    let weight_scalars: Vec<Scalar> = weights.iter().copied().map(embed_u128_to_scalar).collect();
    if !verify_model_commitment(&artifacts.model_commitment, &weight_scalars) {
        return Err("model commitment digest mismatch (legacy weight.json)".into());
    }
    Ok(weight_scalars)
}

fn resolve_public_scalars(artifacts: &ProtocolArtifacts) -> Result<Vec<Scalar>, String> {
    if let Some(ref opening) = artifacts.input_opening {
        if !verify_pedersen_open_input(&artifacts.input_commitment, opening) {
            return Err("input Pedersen opening failed".into());
        }
        return opening_public_scalars(opening);
    }
    let public_inputs = public_inputs_for_network(&artifacts.network);
    if !verify_input_commitment(&artifacts.input_commitment, &public_inputs) {
        return Err("input commitment digest mismatch".into());
    }
    Ok(public_inputs)
}

/// Architecture §6.2 verifier pipeline.
pub fn verifier_pipeline(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    let weight_scalars = resolve_weight_scalars(artifacts)?;
    let public_inputs = resolve_public_scalars(artifacts)?;

    if let Some(ref opening) = artifacts.model_opening {
        let w_star: Vec<u128> = opening
            .weights
            .iter()
            .map(|s| s.parse::<u128>())
            .collect::<Result<_, _>>()
            .map_err(|e| format!("opening weights: {e}"))?;
        if !check_l1_ptmul_bindings(&artifacts.network, &w_star).unwrap_or(false) {
            return Err("L1 PtMul binding check failed".into());
        }
        if let Some(ref expected_root) = artifacts.w_star_merkle_root_hex {
            let root = merkle_root_w_star(&w_star);
            if &root != expected_root {
                return Err("W* Merkle root mismatch".into());
            }
        }
    } else if artifacts.l1_binding_ok == Some(true) {
        let w_star = load_w_star(&artifacts.network).map_err(|e| e.to_string())?;
        if !check_l1_ptmul_bindings(&artifacts.network, &w_star).unwrap_or(false) {
            return Err("L1 binding failed (legacy)".into());
        }
    }

    if let Some(ref mac) = artifacts.mac_proof {
        verify_mac_rlc(mac, artifacts)?;
    }

    let ec = artifacts.ec_proof_view();
    verify_ec_bundle(
        &ec,
        &artifacts.network,
        &artifacts.model_commitment,
        &artifacts.input_commitment,
        &artifacts.client_challenge,
    )?;

    let w_sum: Scalar = weight_scalars.iter().copied().sum();
    let p_sum: Scalar = public_inputs.iter().copied().sum();
    let expected_rlc = rlc_bind_scalars(w_sum, p_sum, &artifacts.client_challenge);
    if hex::encode(expected_rlc.to_bytes()) != artifacts.rlc_binding_hex {
        return Err("RLC binding mismatch".into());
    }

    Ok(())
}

pub fn verifier_run(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    verifier_pipeline(artifacts)
}

pub fn run_full_protocol(network: &str) -> ProtocolArtifacts {
    use crate::load_data;
    use crate::load_data_add;
    use crate::protocol::artifacts::save_artifacts;
    use crate::challenge::ClientChallenge;

    let (num_mults, _, _, _, _) = load_data::load_data(network);
    let (num_adds, _, _, _, _, _) = load_data_add::load_data_add(network);
    let challenge = ClientChallenge::sample(num_adds, num_mults);

    let mut artifacts = crate::prove::pipeline::prover_run(network, challenge);
    verifier_pipeline(&artifacts).expect("client verification must succeed");
    let vstart = SystemTime::now();
    verifier_pipeline(&artifacts).expect("second verification pass");
    artifacts.verify_time_ms = vstart.elapsed().unwrap().as_millis();
    save_artifacts(&artifacts).expect("save artifacts");
    artifacts
}

pub fn setup_and_commit(
    network: &str,
) -> (
    crate::commit::ModelCommitmentBundle,
    crate::commit::InputCommitmentBundle,
    Vec<u128>,
) {
    use crate::commit::{commit_model, commit_public_inputs};
    use crate::model::load_w_star;

    let weights = load_w_star(network).expect("load_w_star");
    let (model_cm, _scalars, _blind) = commit_model(&weights);
    let public_inputs = public_inputs_for_network(network);
    let (input_cm, _blind_in) = commit_public_inputs(&public_inputs);
    (model_cm, input_cm, weights)
}
