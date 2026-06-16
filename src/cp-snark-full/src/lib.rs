pub mod challenge;
pub mod circuit;
pub mod circuit_prove;
pub mod commit;
pub mod commitment;
pub mod curve;
pub mod layer_proof;
pub mod model;
pub mod prove;
pub mod protocol;
pub mod statement;
pub mod trace;
pub mod verify;
pub mod load_data;
pub mod load_data_add;

#[path = "../../proof_generation/vPIN_proof_generation/src/point_addition.rs"]
pub mod point_addition;
#[path = "../../proof_generation/vPIN_proof_generation/src/point_mult.rs"]
pub mod point_mult;
#[path = "../../proof_generation/vPIN_proof_generation/src/commit_test.rs"]
pub mod commit_spartan;

pub use protocol::{
    artifact_path, challenge_from_json, load_artifacts, load_input_binding, prover_pipeline,
    prover_run, prover_with_challenge_json, run_full_protocol, sample_challenge_json,
    save_artifacts, setup_and_commit, verifier_from_path, verifier_pipeline, verifier_run,
    ProtocolArtifacts,
};
