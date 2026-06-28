//! Phase Z.5 / Z.6: canonical Spartan polynomial commitment for `cm_W`.
//!
//! This is the server-side port of
//! `src/cp-snark-full/src/commit/cps.rs::cps_comm_w_star`. Both must produce
//! **byte-identical** commitments for the same `W*` input; a parity test
//! belongs to the cp-snark-full integration test suite.
//!
//! Z.6 wires `CpsCommitment` into the toy verifier
//! ([`crate::circuit::cps_ver`]) so a single canonical `cm_W` is checked
//! against the W* opening that backs the per-layer L1 binding.

use libspartan::dense_mlpoly::{DensePolynomial, PolyCommitment};
use libspartan::scalar::Scalar;
use libspartan::SNARKGens;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::curve::embed_u128_to_scalar;

/// Marker enabling tests to assert the commitment is NOT Pedersen.
pub const CPS_KIND_SPARTAN_PC: &str = "spartan_pc";

/// SNARKGens shape parameters — must match
/// `src/cp-snark-full/src/commit/cps.rs::CPS_GENS_*` exactly so both crates
/// emit byte-identical commitments.
const CPS_GENS_NUM_CONS: usize = 4;
const CPS_GENS_NUM_INPUTS: usize = 0;
const CPS_GENS_NUM_NZ: usize = 8;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CpsCommitment {
    /// SHA-256 digest over the full `poly_comm_hex` vector.
    pub cm_hex: String,
    /// Number of underlying scalars (before zero padding).
    pub num_scalars: usize,
    /// Power-of-two padded length used to build the polynomial.
    pub padded_len: usize,
    /// Spartan PC compressed Ristretto points, hex-encoded.
    pub poly_comm_hex: Vec<String>,
    /// Tag — set to [`CPS_KIND_SPARTAN_PC`] by [`cps_comm_w_star`].
    pub kind: String,
}

#[derive(Clone, Debug)]
pub enum CpsError {
    InvalidInput(String),
}

impl std::fmt::Display for CpsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CpsError::InvalidInput(m) => write!(f, "CPS invalid input: {m}"),
        }
    }
}

impl std::error::Error for CpsError {}

fn next_pow2(n: usize) -> usize {
    let mut k = 1usize;
    while k < n.max(1) {
        k <<= 1;
    }
    k
}

fn digest_poly_comm(comm: &PolyCommitment) -> String {
    let mut h = Sha256::new();
    h.update((comm.C.len() as u64).to_le_bytes());
    for c in &comm.C {
        h.update(c.as_bytes());
    }
    hex::encode(h.finalize())
}

fn build_dense_poly(scalars: &[Scalar]) -> (DensePolynomial, usize) {
    let padded = next_pow2(scalars.len());
    let mut padded_vec: Vec<Scalar> = scalars.to_vec();
    padded_vec.resize(padded, Scalar::zero());
    (DensePolynomial::new(padded_vec), padded)
}

/// Deterministic Spartan PC over a vector of `Scalar`s. Random tape is
/// `None` (zero blinds) so cm_W is purely a function of the input.
fn spartan_pc_commit_scalars(scalars: &[Scalar]) -> (PolyCommitment, usize) {
    let (poly, padded_len) = build_dense_poly(scalars);
    let gens = SNARKGens::new(
        CPS_GENS_NUM_CONS,
        padded_len,
        CPS_GENS_NUM_INPUTS,
        CPS_GENS_NUM_NZ,
    );
    let (poly_comm, _blinds) = poly.commit(&gens.gens_r1cs_sat.gens_pc, None);
    (poly_comm, padded_len)
}

/// Phase Z.5: `cm_W ← CPS.Comm(W*)` via Spartan PC.
pub fn cps_comm_w_star(weights: &[u128]) -> Result<CpsCommitment, CpsError> {
    if weights.is_empty() {
        return Err(CpsError::InvalidInput("empty weights".to_string()));
    }
    let scalars: Vec<Scalar> = weights.iter().copied().map(embed_u128_to_scalar).collect();
    let (poly_comm, padded_len) = spartan_pc_commit_scalars(&scalars);
    let poly_comm_hex: Vec<String> = poly_comm
        .C
        .iter()
        .map(|c| hex::encode(c.as_bytes()))
        .collect();
    let cm_hex = digest_poly_comm(&poly_comm);
    Ok(CpsCommitment {
        cm_hex,
        num_scalars: weights.len(),
        padded_len,
        poly_comm_hex,
        kind: CPS_KIND_SPARTAN_PC.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_w_star() -> Vec<u128> {
        vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 2, 3, 5, 7]
    }

    #[test]
    fn z5_local_cps_comm_uses_spartan_pc() {
        let cm = cps_comm_w_star(&toy_w_star()).expect("commit");
        assert_eq!(cm.kind, CPS_KIND_SPARTAN_PC);
        assert_eq!(cm.num_scalars, 13);
        assert_eq!(cm.padded_len, 16);
        assert!(!cm.poly_comm_hex.is_empty());
    }

    #[test]
    fn z5_local_cps_comm_deterministic() {
        let w = toy_w_star();
        assert_eq!(
            cps_comm_w_star(&w).unwrap(),
            cps_comm_w_star(&w).unwrap(),
            "Spartan PC must be deterministic"
        );
    }

    #[test]
    fn z5_local_cps_comm_rejects_empty() {
        assert!(matches!(
            cps_comm_w_star(&[]),
            Err(CpsError::InvalidInput(_))
        ));
    }
}
