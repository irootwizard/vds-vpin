use std::path::PathBuf;
use std::time::Instant;

use libspartan::scalar::Scalar;
use serde::{Deserialize, Serialize};

use crate::challenge::ClientChallenge;
use crate::commit::{
    commit_model, commit_public_inputs, input_opening_from_commit, model_opening_from_commit,
    verify_input_commitment, verify_model_commitment, InputCommitmentBundle,
    InputCommitmentOpening, ModelCommitmentBundle, ModelCommitmentOpening,
};
use crate::curve::embed_bigint_str_to_scalar;
use crate::prove::ec::prove_ec_batch;
use crate::protocol::artifacts::{ProtocolArtifacts, ProveTiming};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TraceBundleRef {
    pub conv_trace: Option<PathBuf>,
    pub pool_trace: Option<PathBuf>,
    pub fc_trace: Option<PathBuf>,
}

/// Server-side prove input (P4 → P5). γ must originate from client challenge message.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ServerProveInput {
    pub network_id: String,
    pub challenge: ClientChallenge,
    pub cm_w: ModelCommitmentBundle,
    pub cm_x: InputCommitmentBundle,
    pub model_opening: ModelCommitmentOpening,
    pub input_opening: Option<InputCommitmentOpening>,
    pub trace_bundle: TraceBundleRef,
    pub ec_witness_root: Option<PathBuf>,
}

#[derive(Clone, Debug)]
pub struct SetupBundle {
    pub network_id: String,
    pub model_commitment: ModelCommitmentBundle,
    pub input_commitment: InputCommitmentBundle,
    pub model_opening: ModelCommitmentOpening,
    pub weights: Vec<u128>,
}

#[derive(Clone, Debug)]
pub enum ProverError {
    MissingClientGamma,
    Model(String),
    Commitment(String),
    NotImplemented(String),
}

impl std::fmt::Display for ProverError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for ProverError {}

/// Setup: commit model weights and default public inputs (curve coefficient `a`).
pub fn setup_model(network_id: &str, weights: &[u128]) -> Result<SetupBundle, ProverError> {
    let (model_cm, weight_scalars, model_blind) = commit_model(weights);
    if !verify_model_commitment(&model_cm, &weight_scalars) {
        return Err(ProverError::Commitment(
            "model commitment self-check failed".into(),
        ));
    }

    let curve = model_cm.curve_e2.clone();
    let public_inputs = vec![embed_bigint_str_to_scalar(&curve.a)];
    let (input_cm, input_blind) = commit_public_inputs(&public_inputs);
    if !verify_input_commitment(&input_cm, &public_inputs) {
        return Err(ProverError::Commitment(
            "input commitment self-check failed".into(),
        ));
    }

    let model_opening = model_opening_from_commit(weights, &model_blind);
    let _input_opening = input_opening_from_commit(&public_inputs, &input_blind);

    Ok(SetupBundle {
        network_id: network_id.to_string(),
        model_commitment: model_cm,
        input_commitment: input_cm,
        model_opening,
        weights: weights.to_vec(),
    })
}

/// Prove pipeline skeleton: rejects missing client γ; EC prove stub until A1-1/A2-3.
pub fn prove_with_challenge(input: ServerProveInput) -> Result<ProtocolArtifacts, ProverError> {
    if !input.challenge.has_client_gamma() {
        return Err(ProverError::MissingClientGamma);
    }

    let start = Instant::now();
    let weight_scalars: Vec<Scalar> = input
        .model_opening
        .weights
        .iter()
        .map(|s| {
            s.parse::<u128>()
                .map(crate::curve::embed_u128_to_scalar)
                .map_err(|e| ProverError::Model(format!("weight parse: {e}")))
        })
        .collect::<Result<_, _>>()?;

    if !verify_model_commitment(&input.cm_w, &weight_scalars) {
        return Err(ProverError::Commitment(
            "cm_W does not match model opening".into(),
        ));
    }

    let ec_root = input.ec_witness_root.as_deref();
    let (ec_proof, real_ec) = prove_ec_batch(
        &input.network_id,
        &input.cm_w,
        &input.cm_x,
        &input.challenge,
        ec_root,
    );

    let w_sum: Scalar = weight_scalars.iter().copied().sum();
    let public_a = embed_bigint_str_to_scalar(&input.cm_w.curve_e2.a);
    let p_sum = public_a;
    let rlc = w_sum + input.challenge.gamma_scalar() * p_sum;

    let has_traces = input.trace_bundle.conv_trace.is_some()
        || input.trace_bundle.pool_trace.is_some()
        || input.trace_bundle.fc_trace.is_some();
    let proof_coverage = if real_ec && has_traces {
        "ec_plus_scalar_check"
    } else if real_ec {
        "ec_gadget_only"
    } else {
        "skeleton_ec_stub"
    };

    let total_ms = start.elapsed().as_millis();

    Ok(ProtocolArtifacts {
        version: 2,
        network: input.network_id,
        model_commitment: input.cm_w,
        input_commitment: input.cm_x,
        model_opening: Some(input.model_opening),
        input_opening: input.input_opening,
        client_challenge: input.challenge,
        ec_proof: Some(ec_proof.clone()),
        point_add_proof: ec_proof.point_add,
        point_mult_proof: ec_proof.point_mult,
        rlc_binding_hex: hex::encode(rlc.to_bytes()),
        proof_coverage: proof_coverage.to_string(),
        prove_timing: Some(ProveTiming {
            check_scalar_ms: 0,
            prove_mac_ms: 0,
            prove_ec_ms: 0,
            total_ms,
        }),
        prove_time_ms: total_ms,
        verify_time_ms: 0,
    })
}
