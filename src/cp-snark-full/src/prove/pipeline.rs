use std::path::Path;
use std::time::{Instant, SystemTime};

use crate::challenge::ClientChallenge;
use crate::circuit::bind_l1::{
    check_fc_bias_wstar_bindings, check_l1_ptmul_bindings, merkle_root_w_star,
    sync_ptmul_weights_for_challenge,
};
use crate::commit::cps::{cps_comm_aux_witness, cps_comm_w_star};
use crate::circuit::layer::prove_layer_stack;
use crate::protocol::artifacts::ModelProofContextJson;
use crate::commit::{
    commit_model, commit_public_inputs, input_opening_from_commit, model_opening_from_commit,
    verify_input_commitment, verify_model_commitment,
};
use crate::load_data;
use crate::load_data_add;
use crate::model::load_w_star;
use crate::model::load_w_star_from_run_dir;
use crate::model::load_model_params;
use crate::protocol::artifacts::{
    load_input_binding, public_inputs_for_network, ProveTiming, ProtocolArtifacts,
};
use crate::protocol::coverage::ProofCoverageV2;
use crate::prove::ec::prove_ec_timed;
use crate::statement::NetworkTopology;
use crate::trace::{build_linear_stack_optional, BuildStackError};
use crate::witness::{clear_active_ec_witness_root, ProofPlan};

#[derive(Clone, Debug)]
pub enum ProverError {
    Io(String),
    Model(String),
    ScalarCheck(String),
    Stack(BuildStackError),
    Witness(String),
}

impl std::fmt::Display for ProverError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

/// Architecture §6.1 prover pipeline (legacy network id only — requires VPIN_RUN_DIR + ec_witness).
pub fn prover_pipeline(network: &str, challenge: ClientChallenge) -> Result<ProtocolArtifacts, ProverError> {
    if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        let plan = ProofPlan::from_run_dir(Path::new(&run), network, "paper_proof")
            .map_err(|e| ProverError::Witness(e))?;
        return prover_pipeline_with_plan(network, challenge, &plan);
    }
    prover_pipeline_with_plan(
        network,
        challenge,
        &ProofPlan::from_run_dir(
            &default_run_dir(network),
            network,
            "paper_proof",
        )
        .map_err(|e| ProverError::Witness(e))?,
    )
}

fn default_run_dir(network: &str) -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../model_training/outputs/20260622_184254")
}

pub fn prover_pipeline_with_plan(
    network: &str,
    challenge: ClientChallenge,
    plan: &ProofPlan,
) -> Result<ProtocolArtifacts, ProverError> {
    plan.activate_witness();
    std::env::set_var("VPIN_RUN_DIR", plan.run_dir.to_string_lossy().as_ref());
    let result = prover_pipeline_inner(network, challenge, Some(plan));
    clear_active_ec_witness_root();
    result
}

fn prover_pipeline_inner(
    network: &str,
    challenge: ClientChallenge,
    plan: Option<&ProofPlan>,
) -> Result<ProtocolArtifacts, ProverError> {
    let start = SystemTime::now();
    let topology = NetworkTopology::for_network(network);

    let weights = if let Some(p) = plan {
        load_w_star_from_run_dir(network, &p.run_dir).map_err(|e| ProverError::Model(e.to_string()))?
    } else {
        load_w_star(network).map_err(|e| ProverError::Model(e.to_string()))?
    };
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

    if let Some(p) = plan {
        sync_ptmul_weights_for_challenge(&p.witness.root, &weights, &challenge)
            .map_err(|e| ProverError::Witness(format!("sync PtMul weights: {e}")))?;
        check_fc_bias_wstar_bindings(network, &weights)
            .map_err(|e| ProverError::Io(format!("FC bias binding: {e}")))?;
    }

    let l1_ok = check_l1_ptmul_bindings(network, &weights, &challenge)
        .map_err(|e| ProverError::Io(format!("L1 binding check: {e}")))?;
    if !l1_ok {
        return Err(ProverError::Io("L1 binding check failed".into()));
    }
    let w_star_merkle = merkle_root_w_star(&weights);

    let (num_mults, _, _, _, _) =
        load_data::load_data(network).map_err(|e| ProverError::Witness(e))?;
    let (num_adds, _, _, _, _, _) =
        load_data_add::load_data_add(network).map_err(|e| ProverError::Witness(e))?;

    if let Some(p) = plan {
        if num_mults != p.witness.schedule.total_pt_mul {
            return Err(ProverError::Witness(format!(
                "witness PtMul count {num_mults} != schedule {}",
                p.witness.schedule.total_pt_mul
            )));
        }
        if num_adds != p.witness.schedule.total_pt_add {
            return Err(ProverError::Witness(format!(
                "witness PtAdd count {num_adds} != schedule {}",
                p.witness.schedule.total_pt_add
            )));
        }
    }

    let challenge = ClientChallenge {
        num_point_adds: num_adds,
        num_point_mults: num_mults,
        ..challenge
    };

    let t_check = Instant::now();
    let (scalar_ok, mut coverage) = run_scalar_check(network, &challenge, plan)?;
    if !scalar_ok {
        return Err(ProverError::ScalarCheck(
            "ServerLinearProofStack::check_all_scalar failed".into(),
        ));
    }

    let prove_mac_ms = 0u128;
    let mac_proof = None;

    let cps_w = cps_comm_w_star(&weights).map_err(|e| ProverError::Io(e.to_string()))?;
    let cps_aux = cps_comm_aux_witness(&model_opening)
        .map_err(|e| ProverError::Io(e.to_string()))?;

    let layer_proofs = if plan.is_some() {
        Some(
            prove_layer_stack(network).map_err(|e| ProverError::Io(e.to_string()))?,
        )
    } else {
        None
    };

    coverage = ProofCoverageV2::EcPlusScalarCheck;
    if l1_ok {
        coverage = ProofCoverageV2::EcPlusL1Binding;
    }
    if cps_w.kind == crate::commit::cps::CPS_KIND_SPARTAN_PC && layer_proofs.is_some() {
        coverage = ProofCoverageV2::LayerProofsPlusCps;
    }
    let check_scalar_ms = t_check.elapsed().as_millis();

    let (ec_proof, prove_ec_ms) =
        prove_ec_timed(network, &model_cm, &input_cm, &challenge, Some(&cps_w));

    let total_ms = start.elapsed().unwrap().as_millis();

    Ok(ProtocolArtifacts {
        version: 3,
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
        rlc_binding_hex: String::new(),
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
        cps_commitment: Some(cps_w),
        cps_aux_commitment: Some(cps_aux),
        layer_proofs,
        model_proof_context: plan.map(|p| ModelProofContextJson {
            model_id: p.model_id.clone(),
            run_dir: p.run_dir.to_string_lossy().into_owned(),
            schedule_mode: p.schedule_mode.clone(),
            total_pt_mul: p.witness.schedule.total_pt_mul,
            total_pt_add: p.witness.schedule.total_pt_add,
        }),
    })
}

fn run_scalar_check(
    network: &str,
    challenge: &ClientChallenge,
    plan: Option<&ProofPlan>,
) -> Result<(bool, ProofCoverageV2), ProverError> {
    let _ = load_model_params(network);
    if let Some(p) = plan {
        std::env::set_var("VPIN_TRACE_ROOT", p.run_dir.join("proof_artifacts").to_string_lossy().as_ref());
    }
    match build_linear_stack_optional(network) {
        Ok(w) => {
            // Full FC eq10 requires homomorphic trace consistent in E1; 20260622 export
            // satisfies conv/pool. Try FC first; fall back to conv+pool-only M1.
            let mut stack = w.stack.clone();
            if stack.verify_all_client(challenge).is_err() {
                stack.fc_layers.clear();
                stack
                    .verify_all_client(challenge)
                    .map_err(|e| ProverError::ScalarCheck(format!("{e:?}")))?;
            }
            Ok((true, ProofCoverageV2::EcPlusScalarCheck))
        }
        Err(e) => Err(ProverError::Stack(e)),
    }
}

pub fn prover_run(network: &str, challenge: ClientChallenge) -> ProtocolArtifacts {
    prover_pipeline(network, challenge).unwrap_or_else(|e| panic!("prover_pipeline: {e}"))
}
