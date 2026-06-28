pub mod challenge;
pub mod circuit;
pub mod circuit_prove;
pub mod commit;
pub mod curve;
pub mod ec;
pub mod prove;
pub mod protocol;
pub mod trace;

pub mod load_data {
    pub use crate::trace::load_data::{
        ec_witness_root, load_data, load_weights_only, rust_files_root, witness_available,
    };
}
pub mod load_data_add {
    pub use crate::trace::load_data_add::load_data_add;
}

#[path = "../../../../src/proof_generation/vPIN_proof_generation/src/point_addition.rs"]
pub mod point_addition;
#[path = "../../../../src/proof_generation/vPIN_proof_generation/src/point_mult.rs"]
pub mod point_mult;
#[path = "../../../../src/proof_generation/vPIN_proof_generation/src/commit_test.rs"]
pub mod commit_spartan;

pub use challenge::ClientChallenge;
pub use commit::{
    commit_model, commit_public_inputs, verify_pedersen_open_model, InputCommitmentBundle,
    ModelCommitmentBundle, ModelCommitmentOpening,
};
pub use prove::{
    prove_with_challenge, setup_model, ProverError, ServerProveInput, SetupBundle, TraceBundleRef,
};
pub use protocol::artifacts::{load_artifacts, save_artifacts, ProtocolArtifacts};
