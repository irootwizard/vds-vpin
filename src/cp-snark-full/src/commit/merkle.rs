//! Phase Z.10: A′ Merkle commitment **stub**.
//!
//! ## Status: STUB / NON-PROTOCOL
//!
//! Per [`.cursor/plans/vpin_phase_z_密码学闭环_2446a58f.plan.md`] §5 Z.10,
//! this file exists to **document and seal the A′ surface** without
//! claiming the property it would carry in production. **No live code
//! path currently consumes this module.**
//!
//! The current Phase Z protocol path is **B′ = Spartan PC** (see
//! [`crate::commit::cps::cps_comm_w_star`]); the A′ Merkle alternative is
//! intended for *very large* models ($|W| \gtrsim 10^6$) where the
//! Spartan PC pad-to-pow2 dominates prover memory. Until that frontier
//! arrives, A′ is a *non-B′ placeholder*:
//!
//! - **A′ does not** participate in `prove_toy_cps` / `verify_toy_cps_bundle`.
//! - **A′ does not** appear in `proof_coverage` enum values
//!   (`docs/cps-honesty-boundary.md`, Phase Z.11).
//! - **A′ does not** bind to per-layer SNARK transcripts.
//!
//! The included function `merkle_root_4_leaf_sha256` is a textbook
//! SHA-256 binary Merkle root for a 4-leaf fixed-arity tree, used purely
//! to fix the byte ordering and demonstrate the surface compiles. It is
//! NOT the production Poseidon-over-Ristretto MerkleVerify gadget the A′
//! line of work requires; that gadget lives in a future milestone.
//!
//! ### Why a 4-leaf single test?
//!
//! Plan §5 Z.10 explicitly scopes acceptance at "4-leaf Merkle single
//! test", so we lock in the leaf encoding and the parent-hash formula
//! today; expanding to arbitrary arity / Poseidon is deferred.

use sha2::{Digest, Sha256};

/// Per-leaf encoding: SHA-256 of the canonical Spartan-scalar bytes of
/// the leaf payload. Identical to the per-leaf step in
/// `circuit::bind_l1::merkle_root_w_star` so future A′ work can re-use
/// that path.
pub fn merkle_leaf_sha256(leaf_bytes: &[u8]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(leaf_bytes);
    let d = h.finalize();
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&d);
    arr
}

/// Parent-hash helper: `H(left || right)` with SHA-256.
pub fn merkle_parent_sha256(left: &[u8; 32], right: &[u8; 32]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(left);
    h.update(right);
    let d = h.finalize();
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&d);
    arr
}

/// Phase Z.10 stub: compute a 4-leaf SHA-256 Merkle root from raw byte
/// payloads. The arity is fixed at 4 by design — this module is **not**
/// a general Merkle library, only a frozen surface for A′ tracking.
///
/// Leaf order is the slice order. Tree shape:
/// ```text
/// leaves: [L0, L1, L2, L3]
/// level1: [ H(L0 || L1), H(L2 || L3) ]
/// root:    H(level1[0] || level1[1])
/// ```
pub fn merkle_root_4_leaf_sha256(leaves: &[&[u8]; 4]) -> [u8; 32] {
    let l0 = merkle_leaf_sha256(leaves[0]);
    let l1 = merkle_leaf_sha256(leaves[1]);
    let l2 = merkle_leaf_sha256(leaves[2]);
    let l3 = merkle_leaf_sha256(leaves[3]);
    let p01 = merkle_parent_sha256(&l0, &l1);
    let p23 = merkle_parent_sha256(&l2, &l3);
    merkle_parent_sha256(&p01, &p23)
}

/// Marker constant: any callsite enabling A′ would set its
/// `proof_coverage` to include this tag. Today nothing does — keeping
/// the constant only flags future regressions if A′ accidentally turns
/// itself on.
pub const A_PRIME_NOT_LIVE: &str = "a_prime_merkle_stub_only";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn z10_merkle_4_leaf_root_matches_textbook() {
        let leaves: [&[u8]; 4] = [b"alpha", b"beta", b"gamma", b"delta"];
        let root = merkle_root_4_leaf_sha256(&leaves);

        // Reference computation (mirrors merkle_root_4_leaf_sha256 line by line).
        let l0 = merkle_leaf_sha256(b"alpha");
        let l1 = merkle_leaf_sha256(b"beta");
        let l2 = merkle_leaf_sha256(b"gamma");
        let l3 = merkle_leaf_sha256(b"delta");
        let p01 = merkle_parent_sha256(&l0, &l1);
        let p23 = merkle_parent_sha256(&l2, &l3);
        let expected = merkle_parent_sha256(&p01, &p23);

        assert_eq!(root, expected, "Merkle root must equal the textbook fold");
    }

    #[test]
    fn z10_merkle_is_sensitive_to_leaf_swap() {
        let leaves_a: [&[u8]; 4] = [b"alpha", b"beta", b"gamma", b"delta"];
        let leaves_b: [&[u8]; 4] = [b"beta", b"alpha", b"gamma", b"delta"];
        assert_ne!(
            merkle_root_4_leaf_sha256(&leaves_a),
            merkle_root_4_leaf_sha256(&leaves_b),
            "swapping ordered leaves must change the root"
        );
    }

    #[test]
    fn z10_marker_constant_documents_non_live_status() {
        // Defensive: any code path that flips `proof_coverage` to a live
        // A′ value would have to lift this exact string OUT of the
        // codebase, which is intentionally noisy.
        assert_eq!(A_PRIME_NOT_LIVE, "a_prime_merkle_stub_only");
    }
}
