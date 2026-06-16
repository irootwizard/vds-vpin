//! Public input commitment ($\mathsf{cm}_x$) — re-exports from [`crate::commit`].

pub use super::{
    commit_public_inputs, input_opening_from_commit, opening_public_scalars,
    verify_input_commitment, verify_pedersen_open_input, InputCommitmentBundle,
    InputCommitmentOpening, PedersenCommitment,
};
