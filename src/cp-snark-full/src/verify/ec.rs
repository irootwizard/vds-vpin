use crate::challenge::ClientChallenge;
use crate::circuit::ec::{verify_point_add, verify_point_mult, SubCircuitProof};
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::prove::ec::EcProofBundle;

pub fn verify_ec_bundle(
    ec: &EcProofBundle,
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    if let Some(ref add) = ec.point_add {
        verify_point_add(add, network, model, input, challenge)?;
    }
    if let Some(ref mult) = ec.point_mult {
        verify_point_mult(mult, network, model, input, challenge)?;
    }
    Ok(())
}
