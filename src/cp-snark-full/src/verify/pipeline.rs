use std::time::SystemTime;

use libspartan::scalar::Scalar;

use crate::challenge::rlc_bind_scalars;
use crate::circuit::bind_l1::{
    check_fc_bias_wstar_bindings, check_l1_ptmul_bindings, merkle_root_w_star,
    sync_ptmul_weights_for_challenge,
};
use crate::circuit::layer::verify_layer_stack;
use crate::commit::{
    opening_public_scalars, opening_weights_to_scalars, verify_input_commitment,
    verify_model_commitment, verify_pedersen_open_input, verify_pedersen_open_model,
};
use crate::curve::embed_u128_to_scalar;
use crate::protocol::artifacts::{public_inputs_for_network, ProtocolArtifacts};
use crate::trace::build_linear_stack_optional;
use crate::verify::ec::verify_ec_bundle;
use crate::verify::mac::verify_mac_rlc;
use crate::witness::ProofPlan;

/// Resolve weight scalars for verify: prefer artifact opening (R4), else legacy `weight.json`.
fn resolve_weight_scalars(artifacts: &ProtocolArtifacts) -> Result<Vec<Scalar>, String> {
    if let Some(ref opening) = artifacts.model_opening {
        if !verify_pedersen_open_model(&artifacts.model_commitment, opening) {
            return Err("model Pedersen opening failed".into());
        }
        return opening_weights_to_scalars(opening);
    }
    let weights = crate::load_data::load_weights_only(&artifacts.network)?;
    let weight_scalars: Vec<Scalar> = weights.iter().map(|&w| embed_u128_to_scalar(w)).collect();
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

fn activate_run_context(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    if let Some(ref ctx) = artifacts.model_proof_context {
        std::env::set_var("VPIN_RUN_DIR", &ctx.run_dir);
        std::env::set_var(
            "VPIN_TRACE_ROOT",
            format!("{}/proof_artifacts", ctx.run_dir),
        );
        let plan = ProofPlan::from_run_dir(
            std::path::Path::new(&ctx.run_dir),
            &ctx.model_id,
            &ctx.schedule_mode,
        )?;
        plan.activate_witness();
    } else if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        let plan = ProofPlan::from_run_dir(
            std::path::Path::new(&run),
            &artifacts.network,
            "paper_proof",
        )?;
        plan.activate_witness();
    }
    Ok(())
}

fn verify_m1_scalar_stack(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    activate_run_context(artifacts)?;
    let witness = build_linear_stack_optional(&artifacts.network)
        .map_err(|e| format!("build_linear_stack: {e:?}"))?;
    witness
        .stack
        .verify_all_client(&artifacts.client_challenge)
        .map_err(|e| format!("M1 verify_all_client (conv+pool+fc): {e:?}"))?;
    if let Some(ref expected) = artifacts.scalar_trace_digest_hex {
        let actual = crate::trace::scalar_trace_digest_hex(&artifacts.network)?;
        if expected != &actual {
            return Err("scalar_trace_digest mismatch".into());
        }
    }
    Ok(())
}

fn verify_l1_bindings(artifacts: &ProtocolArtifacts, w_star: &[u128]) -> Result<(), String> {
    activate_run_context(artifacts)?;
    if let Some(ref ctx) = artifacts.model_proof_context {
        let plan = ProofPlan::from_run_dir(
            std::path::Path::new(&ctx.run_dir),
            &ctx.model_id,
            &ctx.schedule_mode,
        )?;
        sync_ptmul_weights_for_challenge(
            &plan.witness.root,
            w_star,
            &artifacts.client_challenge,
        )?;
    }
    if !check_l1_ptmul_bindings(&artifacts.network, w_star, &artifacts.client_challenge)? {
        return Err("L1 PtMul binding check failed".into());
    }
    if !check_fc_bias_wstar_bindings(&artifacts.network, w_star)? {
        return Err("FC bias binding check failed".into());
    }
    if let Some(ref expected_root) = artifacts.w_star_merkle_root_hex {
        let root = merkle_root_w_star(w_star);
        if &root != expected_root {
            return Err("W* Merkle root mismatch".into());
        }
    }
    Ok(())
}

/// Architecture §6.2 verifier pipeline.
pub fn verifier_pipeline(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    let weight_scalars = resolve_weight_scalars(artifacts)?;
    let public_inputs = resolve_public_scalars(artifacts)?;

    verify_m1_scalar_stack(artifacts)?;

    if let Some(ref opening) = artifacts.model_opening {
        let w_star: Vec<u128> = opening
            .weights
            .iter()
            .map(|s| s.parse::<u128>())
            .collect::<Result<_, _>>()
            .map_err(|e| format!("opening weights: {e}"))?;
        verify_l1_bindings(artifacts, &w_star)?;
    } else if artifacts.l1_binding_ok == Some(true) {
        let w_star = crate::model::load_w_star(&artifacts.network).map_err(|e| e.to_string())?;
        verify_l1_bindings(artifacts, &w_star)?;
    }

    if let Some(ref mac) = artifacts.mac_proof {
        verify_mac_rlc(mac, artifacts)?;
    }

    if let (Some(ref cm_w), Some(ref opening)) =
        (&artifacts.cps_commitment, &artifacts.model_opening)
    {
        let w_star: Vec<u128> = opening
            .weights
            .iter()
            .map(|s| s.parse::<u128>())
            .collect::<Result<_, _>>()
            .map_err(|e| format!("opening weights: {e}"))?;
        let ok = crate::commit::cps::cps_ver_w_star(&w_star, cm_w)
            .map_err(|e| e.to_string())?;
        if !ok {
            return Err("CPS.Ver(cm_W) failed".into());
        }
    }

    if let Some(ref layers) = artifacts.layer_proofs {
        if !verify_layer_stack(layers) {
            return Err("layer π verify failed".into());
        }
    }

    let ec = artifacts.ec_proof_view();
    verify_ec_bundle(
        &ec,
        &artifacts.network,
        &artifacts.model_commitment,
        &artifacts.input_commitment,
        &artifacts.client_challenge,
        artifacts.cps_commitment.as_ref(),
    )?;

    if !artifacts.rlc_binding_hex.is_empty() {
        let w_sum: Scalar = weight_scalars.iter().copied().sum();
        let p_sum: Scalar = public_inputs.iter().copied().sum();
        let expected_rlc = rlc_bind_scalars(w_sum, p_sum, &artifacts.client_challenge);
        if hex::encode(expected_rlc.to_bytes()) != artifacts.rlc_binding_hex {
            return Err("RLC binding mismatch".into());
        }
    }

    Ok(())
}

pub fn verifier_run(artifacts: &ProtocolArtifacts) -> Result<(), String> {
    verifier_pipeline(artifacts)
}

pub fn run_full_protocol(network: &str) -> ProtocolArtifacts {
    use crate::challenge::ClientChallenge;
    use crate::load_data;
    use crate::load_data_add;
    use crate::protocol::artifacts::save_artifacts;
    use crate::witness::{clear_active_ec_witness_root, ProofPlan};

    let run_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../model_training/outputs/20260622_184254");
    let plan = ProofPlan::from_run_dir(&run_dir, network, "paper_proof")
        .expect("ProofPlan from standard run");
    plan.activate_witness();
    std::env::set_var("VPIN_RUN_DIR", plan.run_dir.to_string_lossy().as_ref());

    let (num_mults, _, _, _, _) =
        load_data::load_data(network).expect("load_data for run_full_protocol");
    let (num_adds, _, _, _, _, _) =
        load_data_add::load_data_add(network).expect("load_data_add for run_full_protocol");
    let challenge = ClientChallenge::sample(num_adds, num_mults);

    let mut artifacts = crate::prove::pipeline::prover_run(network, challenge);
    verifier_pipeline(&artifacts).expect("client verification must succeed");
    let vstart = SystemTime::now();
    verifier_pipeline(&artifacts).expect("second verification pass");
    artifacts.verify_time_ms = vstart.elapsed().unwrap().as_millis();
    save_artifacts(&artifacts).expect("save artifacts");
    clear_active_ec_witness_root();
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
