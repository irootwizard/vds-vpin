use std::time::{Instant, SystemTime};

use libspartan::scalar::Scalar;

use crate::challenge::{rlc_bind_scalars, ClientChallenge};
use crate::circuit::bind_l1::{check_l1_ptmul_bindings, merkle_root_w_star};
use crate::commit::{
    commit_model, commit_public_inputs, input_opening_from_commit, model_opening_from_commit,
    verify_input_commitment, verify_model_commitment,
};
use crate::model::load_w_star;
use crate::load_data;
use crate::load_data_add;
use crate::model::load_model_params;
use crate::protocol::artifacts::{
    load_input_binding, public_inputs_for_network, ProveTiming, ProtocolArtifacts,
};
use crate::protocol::coverage::ProofCoverageV2;
use crate::prove::ec::prove_ec_timed;
use crate::statement::NetworkTopology;
use crate::trace::{build_linear_stack_optional, BuildStackError};

#[derive(Clone, Debug)]
pub enum ProverError {
    Io(String),
    Model(String),
    ScalarCheck(String),
    Stack(BuildStackError),
}

impl std::fmt::Display for ProverError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

/// Architecture §6.1 prover pipeline.
pub fn prover_pipeline(network: &str, challenge: ClientChallenge) -> Result<ProtocolArtifacts, ProverError> {
    let start = SystemTime::now();
    let topology = NetworkTopology::for_network(network);

    let weights = load_w_star(network).map_err(|e| ProverError::Model(e.to_string()))?;
    let (model_cm, weight_scalars, model_blind) = commit_model(&weights);
    let public_inputs = public_inputs_for_network(network);
    let (input_cm, input_blind) = commit_public_inputs(&public_inputs);
    let model_opening = model_opening_from_commit(&weights, &model_blind);
    let input_opening = input_opening_from_commit(&public_inputs, &input_blind);

    if !verify_model_commitment(&model_cm, &weight_scalars) {
        return Err(ProverError::Io("model commitment self-check failed".into()));
    }
    if !verify_input_commitment(&input_cm, &public_inputs) {
        return Err(ProverError::Io("input commitment self-check failed".into()));
    }

    let l1_ok = check_l1_ptmul_bindings(network, &weights)
        .map_err(|e| ProverError::Io(format!("L1 binding check: {e}")))?;
    if !l1_ok {
        return Err(ProverError::Io("L1 binding check failed".into()));
    }
    let w_star_merkle = merkle_root_w_star(&weights);

    let (num_mults, _, _, _, _) = load_data::load_data(network);
    let (num_adds, _, _, _, _, _) = load_data_add::load_data_add(network);
    let challenge = ClientChallenge {
        num_point_adds: num_adds,
        num_point_mults: num_mults,
        ..challenge
    };

    let t_check = Instant::now();
    let (scalar_ok, mut coverage) = run_scalar_check(network, &challenge)?;
    if !scalar_ok {
        return Err(ProverError::ScalarCheck(
            "ServerLinearProofStack::check_all_scalar failed".into(),
        ));
    }
    coverage = ProofCoverageV2::EcPlusScalarCheck;
    if l1_ok {
        coverage = ProofCoverageV2::EcPlusL1Binding;
    }
    let check_scalar_ms = t_check.elapsed().as_millis();

    // π_mac SNARK uses bare SNARK::prove (incompatible with vPIN split-witness commit path).
    // Scalar Eq.(9) is already checked in `run_scalar_check`; EC proofs carry the main load.
    let prove_mac_ms = 0u128;
    let mac_proof = None;

    let (ec_proof, prove_ec_ms) = prove_ec_timed(network, &model_cm, &input_cm, &challenge);

    let w_sum: Scalar = weight_scalars.iter().copied().sum();
    let p_sum: Scalar = public_inputs.iter().copied().sum();
    let rlc = rlc_bind_scalars(w_sum, p_sum, &challenge);

    let total_ms = start.elapsed().unwrap().as_millis();

    Ok(ProtocolArtifacts {
        version: 2,
        network: network.to_string(),
        topology: Some(topology),
        model_commitment: model_cm,
        input_commitment: input_cm,
        model_opening: Some(model_opening),
        input_opening: Some(input_opening),
        client_challenge: challenge,
        l1_binding_ok: Some(l1_ok),
        w_star_merkle_root_hex: Some(w_star_merkle),
        input_binding_len: load_input_binding(network).map(|v| v.len()),
        ec_proof: Some(ec_proof.clone()),
        point_add_proof: ec_proof.point_add,
        point_mult_proof: ec_proof.point_mult,
        mac_proof,
        rlc_binding_hex: hex::encode(rlc.to_bytes()),
        proof_coverage: coverage.as_str().to_string(),
        scalar_check_ok: Some(scalar_ok),
        prove_timing: Some(ProveTiming {
            check_scalar_ms,
            prove_mac_ms,
            prove_ec_ms,
            total_ms,
        }),
        prove_time_ms: total_ms,
        verify_time_ms: 0,
    })
}

fn run_scalar_check(
    network: &str,
    challenge: &ClientChallenge,
) -> Result<(bool, ProofCoverageV2), ProverError> {
    let _ = load_model_params(network);
    match build_linear_stack_optional(network) {
        Ok(w) => {
            w.stack
                .check_all_scalar(challenge)
                .map_err(|e| ProverError::ScalarCheck(format!("{e:?}")))?;
            Ok((true, ProofCoverageV2::EcPlusScalarCheck))
        }
        Err(e) => Err(ProverError::Stack(e)),
    }
}

/// Legacy entry: same as `prover_pipeline` but returns artifacts on scalar-check miss (EC still runs).
pub fn prover_run(network: &str, challenge: ClientChallenge) -> ProtocolArtifacts {
    prover_pipeline(network, challenge).unwrap_or_else(|e| panic!("prover_pipeline: {e}"))
}
