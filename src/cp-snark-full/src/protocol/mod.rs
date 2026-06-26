//! CP-SNARK protocol orchestration (artifacts, prover, verifier).

pub mod artifacts;
pub mod coverage;
pub mod cross_process;

pub use artifacts::{
    artifact_path, artifacts_dir, load_artifacts, load_input_binding, public_inputs_for_network,
    save_artifacts, ProveTiming, ProtocolArtifacts,
};
pub use cross_process::{
    challenge_from_json, prover_with_challenge_json, sample_challenge_json, verifier_from_path,
};
pub use crate::prove::pipeline::{prover_pipeline, prover_run};
pub use crate::verify::pipeline::{run_full_protocol, setup_and_commit, verifier_pipeline, verifier_run};
