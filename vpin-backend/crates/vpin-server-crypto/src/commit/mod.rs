//! Pedersen-style commitments for model weights and public inputs.

mod pedersen;

pub use pedersen::{
    append_commitments_to_transcript, commit_model, commit_public_inputs,
    input_opening_from_commit, model_opening_from_commit, opening_public_scalars,
    opening_weights_to_scalars, verify_input_commitment, verify_model_commitment,
    verify_pedersen_open_input, verify_pedersen_open_model, InputCommitmentBundle,
    InputCommitmentOpening, ModelCommitmentBundle, ModelCommitmentOpening, PedersenCommitment,
};
