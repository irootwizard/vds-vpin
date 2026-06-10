//! EC gadget prove — Spartan batch when rust_files witness present.

use std::path::Path;
use std::time::Instant;

use crate::challenge::ClientChallenge;
use crate::circuit_prove::{
    prove_point_add, prove_point_add_with_cm_w, prove_point_mult, prove_point_mult_with_cm_w,
    verify_point_add, verify_point_add_with_cm_w, verify_point_mult, verify_point_mult_with_cm_w,
};
use crate::commit::cps::CpsCommitment;
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::protocol::artifacts::EcProofBundle;
use crate::trace::{load_data, load_data_add, witness_available};

/// Returns `true` when the user explicitly asked for a real EC prove via
/// the `VPIN_EC_REAL_PROVE=1` env var, **regardless** of whether a
/// witness directory was supplied. Tests gate on this so they can assert
/// the request was honored even on the toy network (which has no witness
/// JSON).
pub fn vpin_ec_real_prove_requested() -> bool {
    std::env::var("VPIN_EC_REAL_PROVE").ok().as_deref() == Some("1")
}

fn real_ec_prove_enabled(ec_witness_root: Option<&Path>) -> bool {
    if vpin_ec_real_prove_requested() {
        return true;
    }
    ec_witness_root.is_some_and(|p| p.is_dir())
}

/// Prove PtAdd/PtMult SNARKs when witness JSON exists and real prove is requested.
pub fn prove_ec_batch(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    ec_witness_root: Option<&Path>,
) -> (EcProofBundle, bool) {
    prove_ec_batch_with_cm_w(network, None, model, input, challenge, ec_witness_root)
}

/// Phase Z.8: same as [`prove_ec_batch`] but threads `cm_W` (Spartan PC)
/// into the EC SNARK transcript so the layer and EC paths bind to the
/// same model identity.
pub fn prove_ec_batch_with_cm_w(
    network: &str,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    ec_witness_root: Option<&Path>,
) -> (EcProofBundle, bool) {
    if !witness_available(network) || !real_ec_prove_enabled(ec_witness_root) {
        return (prove_ec_batch_stub(network, model, input, challenge), false);
    }

    let (num_mults, _, _, _, _) = load_data(network);
    let (num_adds, _, _, _, _, _) = load_data_add(network);

    let add = if num_adds > 0 {
        Some(prove_point_add_with_cm_w(
            network, cps_cm_w, model, input, challenge,
        ))
    } else {
        None
    };

    let mult = if num_mults > 0 && network != "L2" && network != "L4" {
        Some(prove_point_mult_with_cm_w(
            network, cps_cm_w, model, input, challenge,
        ))
    } else {
        None
    };

    (
        EcProofBundle {
            point_add: add,
            point_mult: mult,
        },
        true,
    )
}

/// Stub EC prove: records counts only; used when witness missing or fast path.
pub fn prove_ec_batch_stub(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> EcProofBundle {
    let (num_adds, _) = crate::ec::point_add_counts(network);
    let (num_mults, _) = crate::ec::point_mult_counts(network);
    let _ = (model, input, challenge, num_adds, num_mults);
    EcProofBundle {
        point_add: None,
        point_mult: None,
    }
}

pub fn prove_ec_timed(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    ec_witness_root: Option<&Path>,
) -> (EcProofBundle, u128, bool) {
    let t0 = Instant::now();
    let (bundle, real) = prove_ec_batch(network, model, input, challenge, ec_witness_root);
    (bundle, t0.elapsed().as_millis(), real)
}

pub fn verify_ec_bundle(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    bundle: &EcProofBundle,
) -> bool {
    verify_ec_bundle_with_cm_w(network, None, model, input, challenge, bundle)
}

pub fn verify_ec_bundle_with_cm_w(
    network: &str,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    bundle: &EcProofBundle,
) -> bool {
    let add_ok = match &bundle.point_add {
        Some(p) => {
            verify_point_add_with_cm_w(p, network, cps_cm_w, model, input, challenge).is_ok()
        }
        None => true,
    };
    let mult_ok = match &bundle.point_mult {
        Some(p) => {
            verify_point_mult_with_cm_w(p, network, cps_cm_w, model, input, challenge).is_ok()
        }
        None => true,
    };
    add_ok && mult_ok
}
