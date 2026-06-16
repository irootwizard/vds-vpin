use std::time::Instant;

use crate::challenge::ClientChallenge;
use crate::circuit::ec::{prove_point_add, prove_point_mult, SubCircuitProof};
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::load_data;
use crate::load_data_add;

#[derive(Clone, Debug, Default, serde::Serialize, serde::Deserialize)]
pub struct EcProofBundle {
    pub point_add: Option<SubCircuitProof>,
    pub point_mult: Option<SubCircuitProof>,
}

pub fn prove_ec_batch(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> EcProofBundle {
    let (num_mults, _, _, _, _) = load_data::load_data(network);
    let (num_adds, _, _, _, _, _) = load_data_add::load_data_add(network);

    let add = if num_adds > 0 {
        Some(prove_point_add(network, model, input, challenge))
    } else {
        None
    };

    let mult = if num_mults > 0 && network != "L2" && network != "L4" {
        Some(prove_point_mult(network, model, input, challenge))
    } else {
        None
    };

    EcProofBundle {
        point_add: add,
        point_mult: mult,
    }
}

pub fn prove_ec_timed(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> (EcProofBundle, u128) {
    let t0 = Instant::now();
    let bundle = prove_ec_batch(network, model, input, challenge);
    (bundle, t0.elapsed().as_millis())
}
