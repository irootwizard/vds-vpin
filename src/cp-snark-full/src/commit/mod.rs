//! Model / input commitments and transcript binding (paper Setup).

pub mod cps;
pub mod input;
pub mod model;
pub mod transcript;

pub use input::{
    commit_public_inputs, input_opening_from_commit, verify_input_commitment,
    verify_pedersen_open_input, InputCommitmentBundle, InputCommitmentOpening,
};
pub use model::{
    commit_model, model_opening_from_commit, opening_weights_to_scalars, verify_model_commitment,
    verify_pedersen_open_model, ModelCommitmentBundle, ModelCommitmentOpening, PedersenCommitment,
};
pub use crate::commitment::opening_public_scalars;
pub use transcript::{append_commitments_to_transcript, decompress_commitment};
