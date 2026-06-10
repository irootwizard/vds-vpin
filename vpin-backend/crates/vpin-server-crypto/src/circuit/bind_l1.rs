//! L1 weight binding (full implementation lands in Z.4).
//!
//! Placeholder module so [`crate::circuit::mod`] compiles ahead of Z.4.

use libspartan::scalar::Scalar;

use crate::curve::embed_u128_to_scalar;

/// Returns whether the supplied scalar matches the canonical `u128` embedding
/// expected by the L1 binding. Used by Z.4 negative tests to detect weight
/// tampering.
pub fn embed_matches(weight: u128, scalar: &Scalar) -> bool {
    embed_u128_to_scalar(weight) == *scalar
}
