//! M4: prove EC layer when manifest present (wraps batch prove).

use std::path::Path;

use crate::challenge::ClientChallenge;
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::protocol::artifacts::EcProofBundle;
use crate::prove::ec::{prove_ec_batch, prove_ec_batch_stub};
use crate::trace::rust_files_root;

pub fn manifest_path(network: &str) -> std::path::PathBuf {
    rust_files_root()
        .join(network)
        .join("pointMult")
        .join("manifest.json")
}

pub fn prove_ec_layer(
    network: &str,
    _layer_index: u8,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    witness_root: Option<&Path>,
) -> Result<EcProofBundle, String> {
    if !manifest_path(network).is_file() {
        return Ok(prove_ec_batch_stub(network, model, input, challenge));
    }
    let (bundle, _) = prove_ec_batch(network, model, input, challenge, witness_root);
    Ok(bundle)
}
