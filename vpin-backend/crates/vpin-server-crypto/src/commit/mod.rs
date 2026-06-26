//! Pedersen-style commitments for model weights and public inputs, plus
//! the Phase Z canonical Spartan PC `cm_W` (`cps_comm_w_star`).

mod pedersen;
pub mod cps;

pub use pedersen::{
    append_commitments_to_transcript, commit_model, commit_public_inputs,
    input_opening_from_commit, model_opening_from_commit, opening_public_scalars,
    opening_weights_to_scalars, verify_input_commitment, verify_model_commitment,
    verify_pedersen_open_input, verify_pedersen_open_model, InputCommitmentBundle,
    InputCommitmentOpening, ModelCommitmentBundle, ModelCommitmentOpening, PedersenCommitment,
};

pub use cps::{cps_comm_w_star, CpsCommitment, CpsError, CPS_KIND_SPARTAN_PC};
