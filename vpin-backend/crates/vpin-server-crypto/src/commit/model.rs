//! Model weight commitment ($\mathsf{cm}_W$) — re-exports from [`crate::commit`].

pub use super::{
    commit_model, model_opening_from_commit, opening_weights_to_scalars,
    verify_model_commitment, verify_pedersen_open_model, ModelCommitmentBundle,
    ModelCommitmentOpening, PedersenCommitment,
};
