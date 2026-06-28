//! M-B′: Spartan CPS.Comm / CPS.Ver.
//!
//! Phase Z.5 replaces the Pedersen MVP of `cps_comm_w_star` with a real
//! Spartan polynomial commitment (PC) over the model weight vector W*:
//!
//! 1. Embed W* into Spartan field scalars via `embed_u128_to_scalar`.
//! 2. Pad to the next power of two and build a `DensePolynomial`.
//! 3. Commit using `DensePolynomial::commit(gens.gens_r1cs_sat.gens_pc, tape)`.
//! 4. Surface the full compressed-Ristretto vector (`PolyCommitment.C`) plus
//!    a SHA-256 digest binding all PC points as the canonical `cm_hex`.
//!
//! This is the **same primitive** used by the layer prover
//! (`circuit_prove.rs` → `comm_vars_para`), so a downstream `CPS.Ver`
//! (Phase Z.6) can reuse Spartan's PC machinery to bind cm_W to each
//! layer's W*-rooted witness.
//!
//! The legacy Pedersen `commit_model` still exists for diagnostics
//! (`commit_model_pedersen_for_diff` test helper); the protocol layer now
//! treats Spartan PC as the canonical `cm_W`.

use std::time::Instant;

use libspartan::dense_mlpoly::{DensePolynomial, PolyCommitment};
use libspartan::random::RandomTape;
use libspartan::scalar::Scalar;
use libspartan::SNARKGens;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::commit::{
    commit_model, opening_weights_to_scalars, ModelCommitmentBundle, ModelCommitmentOpening,
};
use crate::commit_spartan::my_dense_mlpoly_commit;
use crate::curve::embed_u128_to_scalar;

/// Marker that downstream code (and tests) can use to assert we are no
/// longer producing Pedersen-style commitments for `cm_W`.
pub const CPS_KIND_SPARTAN_PC: &str = "spartan_pc";

/// Deterministic SNARKGens shape parameters for `cps_comm_w_star`.
///
/// `num_vars` is sized dynamically to the padded weight length. We deliberately
/// pin `num_inputs = 0` so SNARKGens' internal `max(num_vars, num_inputs + 1)`
/// does not silently inflate `num_vars_padded` (which would make the
/// `MultiCommitGens.n` chunk size disagree with the `DensePolynomial` row
/// slice length for the `padded_len == 1` corner case). The other dimensions
/// only influence `gens_r1cs_eval`, which we don't consume.
const CPS_GENS_NUM_CONS: usize = 4;
const CPS_GENS_NUM_INPUTS: usize = 0;
const CPS_GENS_NUM_NZ: usize = 8;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CpsCommitment {
    /// SHA-256 digest over all `poly_comm_hex` entries (compressed Ristretto
    /// points). Acts as a stable, finger-printable handle for cm_W; changing
    /// any underlying scalar flips this byte-for-byte (cf. Spartan PC
    /// binding).
    pub cm_hex: String,
    /// Number of real scalars committed (before zero-padding).
    pub num_scalars: usize,
    /// Power-of-two padded length used to build the `DensePolynomial`.
    pub padded_len: usize,
    /// Full Spartan PC compressed Ristretto points, hex-encoded; consumed by
    /// `CPS.Ver` (Z.6) to rebuild `PolyCommitment`.
    pub poly_comm_hex: Vec<String>,
    /// Explicit tag — set to [`CPS_KIND_SPARTAN_PC`] by `cps_comm_w_star`.
    pub kind: String,
}

#[derive(Clone, Debug)]
pub enum CpsError {
    NotImplemented(&'static str),
    InvalidInput(String),
}

impl std::fmt::Display for CpsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CpsError::NotImplemented(m) => write!(f, "CPS not implemented: {m}"),
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

fn build_dense_poly_for_weights(scalars: &[Scalar]) -> (DensePolynomial, usize) {
    let padded = next_pow2(scalars.len());
    let mut padded_vec: Vec<Scalar> = scalars.to_vec();
    padded_vec.resize(padded, Scalar::zero());
    (DensePolynomial::new(padded_vec), padded)
}

/// Commit a vector of `Scalar`s with the Spartan polynomial commitment.
///
/// Shared helper used by `cps_comm_w_star` and tests so the same code path
/// is exercised everywhere. Returns the raw `PolyCommitment` together with
/// the padded length so the caller can format the public `CpsCommitment`.
///
/// We deliberately pass `random_tape: None` (= zero blinds): cm_W must be a
/// **deterministic** function of W* so the client can persist it across
/// sessions. Spartan's PC remains binding under DLOG without hiding blinds;
/// the model is then computationally hiding through the secrecy of W*.
pub(crate) fn spartan_pc_commit_scalars(scalars: &[Scalar]) -> (PolyCommitment, usize) {
    let (poly, padded_len) = build_dense_poly_for_weights(scalars);
    let gens = SNARKGens::new(
        CPS_GENS_NUM_CONS,
        padded_len,
        CPS_GENS_NUM_INPUTS,
        CPS_GENS_NUM_NZ,
    );
    let (poly_comm, _blinds) = poly.commit(&gens.gens_r1cs_sat.gens_pc, None);
    (poly_comm, padded_len)
}

/// B′.1: `cm_W ← CPS.Comm(W*)` via **Spartan polynomial commitment**.
///
/// Returns a `CpsCommitment` whose `kind == [CPS_KIND_SPARTAN_PC]` — i.e.
/// not Pedersen. The full PC vector is included so a verifier (Z.6) can
/// re-derive the digest and feed the points into `comm_vars_para`.
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

/// B′.2: `cm' ← CPS.Comm(aux witness blocks)` — partial via
/// `my_dense_mlpoly_commit`.
pub fn cps_comm_aux_witness(opening: &ModelCommitmentOpening) -> Result<CpsCommitment, CpsError> {
    let scalars =
        opening_weights_to_scalars(opening).map_err(|_| CpsError::NotImplemented("opening parse"))?;
    if scalars.is_empty() {
        return Err(CpsError::InvalidInput("empty aux witness".to_string()));
    }
    let num_scalars = scalars.len();
    let (poly, padded_len) = build_dense_poly_for_weights(&scalars);
    let gens = SNARKGens::new(
        CPS_GENS_NUM_CONS,
        padded_len,
        CPS_GENS_NUM_INPUTS,
        CPS_GENS_NUM_NZ,
    );
    let mut tape = RandomTape::new(b"cps_aux");
    let (_comm_para, blind_para) = poly.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut tape));
    let mut tape2 = RandomTape::new(b"cps_aux_input");
    let (_comm_input, blind_input) = poly.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut tape2));
    let (comm_vars, _blinds) = my_dense_mlpoly_commit(
        &poly,
        &gens.gens_r1cs_sat.gens_pc,
        blind_para.blinds.clone(),
        blind_input.blinds.clone(),
    );
    let poly_comm_hex: Vec<String> = comm_vars
        .C
        .iter()
        .map(|c| hex::encode(c.as_bytes()))
        .collect();
    let cm_hex = digest_poly_comm(&comm_vars);
    Ok(CpsCommitment {
        cm_hex,
        num_scalars,
        padded_len,
        poly_comm_hex,
        kind: CPS_KIND_SPARTAN_PC.to_string(),
    })
}

/// Verify `cm_W` matches a recomputed Spartan PC over opened weights.
pub fn cps_ver_w_star(weights: &[u128], cm: &CpsCommitment) -> Result<bool, CpsError> {
    let recomputed = cps_comm_w_star(weights)?;
    Ok(recomputed.cm_hex == cm.cm_hex
        && recomputed.kind == cm.kind
        && recomputed.num_scalars == cm.num_scalars)
}

/// B′.3: verify CPS commitments against opened W* (π wiring deferred to layer proofs).
pub fn cps_ver_opening(
    weights: &[u128],
    cm_w: &CpsCommitment,
    cm_aux: Option<&CpsCommitment>,
    opening: &ModelCommitmentOpening,
) -> Result<bool, CpsError> {
    if !cps_ver_w_star(weights, cm_w)? {
        return Ok(false);
    }
    if let Some(aux) = cm_aux {
        let recomputed = cps_comm_aux_witness(opening)?;
        if recomputed.cm_hex != aux.cm_hex {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Diagnostics-only: a fresh Pedersen commit over the same weight vector,
/// used by tests asserting that Z.5 has moved off Pedersen.
#[doc(hidden)]
pub fn commit_model_pedersen_for_diff(weights: &[u128]) -> String {
    let (bundle, _, _): (ModelCommitmentBundle, _, _) = commit_model(weights);
    bundle.cm_weights.point_hex
}

/// Helper used by `tests/cps_z5_spartan_pc.rs`: time a single Spartan PC
/// commitment over `weights` and return `(prove_ms, commitment_bytes)`.
pub fn time_cps_comm_w_star(weights: &[u128]) -> Result<(u128, usize), CpsError> {
    let t0 = Instant::now();
    let cm = cps_comm_w_star(weights)?;
    let prove_ms = t0.elapsed().as_millis();
    let bytes = cm.poly_comm_hex.iter().map(|h| h.len() / 2).sum::<usize>();
    Ok((prove_ms, bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_weights() -> Vec<u128> {
        // Toy network W* (13 scalars: 9 conv filter + 2 fc weights + 2 fc bias).
        vec![1, 0, 1, 2, 0, 2, 1, 0, 1, 3, 5, 7, 11]
    }

    #[test]
    fn z5_cps_comm_w_star_uses_spartan_pc_kind() {
        let cm = cps_comm_w_star(&toy_weights()).expect("commit toy W*");
        assert_eq!(cm.kind, CPS_KIND_SPARTAN_PC);
        assert_eq!(cm.num_scalars, 13);
        assert_eq!(cm.padded_len, 16);
        assert!(!cm.poly_comm_hex.is_empty(), "poly_comm_hex must be non-empty");
        assert!(!cm.cm_hex.is_empty());
    }

    #[test]
    fn z5_cps_comm_w_star_is_deterministic() {
        let w = toy_weights();
        let a = cps_comm_w_star(&w).expect("a");
        let b = cps_comm_w_star(&w).expect("b");
        assert_eq!(a, b, "Spartan PC must be deterministic for same input");
    }

    #[test]
    fn z5_cps_comm_w_star_distinct_from_pedersen() {
        let w = toy_weights();
        let pc = cps_comm_w_star(&w).expect("spartan");
        let ped = commit_model_pedersen_for_diff(&w);
        // Pedersen returns a single 32-byte point (64 hex chars).
        // Spartan PC has multiple points; even the cm_hex digest must
        // differ from the Pedersen 32-byte hex by construction.
        assert!(
            pc.poly_comm_hex.len() >= 1,
            "Spartan PC must surface ≥1 group element"
        );
        assert_ne!(pc.cm_hex, ped, "cps_comm_w_star must not equal Pedersen point_hex");
        assert_ne!(pc.poly_comm_hex.first().cloned().unwrap_or_default(), ped);
    }

    #[test]
    fn z5_cps_comm_w_star_sensitive_to_weight_changes() {
        let mut w = toy_weights();
        let base = cps_comm_w_star(&w).expect("base");
        w[3] = 99;
        let tampered = cps_comm_w_star(&w).expect("tampered");
        assert_ne!(
            base.cm_hex, tampered.cm_hex,
            "tampering W* must change cm_hex"
        );
        assert_ne!(
            base.poly_comm_hex, tampered.poly_comm_hex,
            "tampering W* must change Spartan PC points"
        );
    }

    #[test]
    fn z5_cps_comm_w_star_padding_pow2() {
        // 1, 2, 3, 5, 8, 13, 16, 17 → padded to 1, 2, 4, 8, 8, 16, 16, 32
        let cases: &[(usize, usize)] =
            &[(1, 1), (2, 2), (3, 4), (5, 8), (8, 8), (13, 16), (16, 16), (17, 32)];
        for &(n, expected) in cases {
            let w: Vec<u128> = (0..n).map(|i| (i as u128) + 1).collect();
            let cm = cps_comm_w_star(&w).expect("commit");
            assert_eq!(cm.num_scalars, n, "num_scalars for n={n}");
            assert_eq!(cm.padded_len, expected, "padded_len for n={n}");
        }
    }

    #[test]
    fn z5_cps_comm_w_star_rejects_empty() {
        let err = cps_comm_w_star(&[]).unwrap_err();
        match err {
            CpsError::InvalidInput(m) => assert!(m.contains("empty")),
            other => panic!("expected InvalidInput, got {other:?}"),
        }
    }

    #[test]
    fn z5_cps_ver_rejects_wrong_kind() {
        let mut cm_w = cps_comm_w_star(&toy_weights()).expect("cm_w");
        let opening = {
            let (_, _, blind) = commit_model(&toy_weights());
            crate::commit::model_opening_from_commit(&toy_weights(), &blind)
        };
        cm_w.kind = "pedersen_legacy".to_string();
        let res = cps_ver_opening(&toy_weights(), &cm_w, None, &opening).expect("check");
        assert!(!res, "verifier must refuse non-Spartan kind mismatch via recompute");
    }

    #[test]
    fn z5_cps_ver_opening_honest() {
        let w = toy_weights();
        let cm_w = cps_comm_w_star(&w).expect("cm_w");
        assert!(cps_ver_w_star(&w, &cm_w).expect("ver"));
    }

    #[test]
    fn z5_cps_comm_aux_witness_uses_spartan_pc() {
        let w = toy_weights();
        let (_, _, blind) = commit_model(&w);
        let opening = crate::commit::model_opening_from_commit(&w, &blind);
        let aux = cps_comm_aux_witness(&opening).expect("aux");
        assert_eq!(aux.kind, CPS_KIND_SPARTAN_PC);
        assert_eq!(aux.num_scalars, 13);
        assert!(!aux.poly_comm_hex.is_empty());
    }
}
