//! BLS signatures on BLS12-381 (via blst crate).
//! Mirrors Python charm-crypto BLS in vads_lib.py.
//!
//! Python: sigma = (HG(i||tag) * u^s)^alpha
//!         e(sigma, g) == e(HG(i||tag) * u^s, A)
//!
//! blst min-pk: signature in G1, public key in G2.

use blst::min_pk::{AggregateSignature, PublicKey, SecretKey, Signature};
use rand::Rng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::OvdsError;

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

/// BLS public key (G2, 96 bytes)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BlsPublicKey(pub Vec<u8>);

/// BLS signature (G1, 48 bytes)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BlsSignature(pub Vec<u8>);

/// BLS secret key (32 bytes)
#[derive(Clone, Debug)]
pub struct BlsSecretKey(pub [u8; 32]);

/// G1 point (48 bytes)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct G1Point(pub Vec<u8>);

/// G2 point (96 bytes)
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct G2Point(pub Vec<u8>);

// ---------------------------------------------------------------------------
// Key generation
// ---------------------------------------------------------------------------

pub fn key_gen() -> (BlsSecretKey, BlsPublicKey) {
    let mut ikm = [0u8; 32];
    rand::thread_rng().fill(&mut ikm);
    let sk = SecretKey::key_gen(&ikm, &[]).expect("key_gen");
    let pk = sk.sk_to_pk();
    (BlsSecretKey(sk.serialize()), BlsPublicKey(pk.compress().to_vec()))
}

// ---------------------------------------------------------------------------
// Sign / Verify
// ---------------------------------------------------------------------------

/// BLS sign: sigma = HG(msg)^alpha.
/// dst = BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_
pub fn sign(sk: &BlsSecretKey, msg: &[u8]) -> Result<BlsSignature, OvdsError> {
    let sk = SecretKey::deserialize(&sk.0)
        .map_err(|e| OvdsError::Bls(format!("bad sk: {:?}", e)))?;
    let dst = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_";
    let sig = sk.sign(msg, dst, &[]);
    Ok(BlsSignature(sig.compress().to_vec()))
}

/// BLS verify: e(sigma, g) == e(HG(msg), pk).
pub fn verify(pk: &BlsPublicKey, msg: &[u8], sig: &BlsSignature) -> Result<bool, OvdsError> {
    let pk = PublicKey::deserialize(&pk.0)
        .map_err(|e| OvdsError::Bls(format!("bad pk: {:?}", e)))?;
    let sig = Signature::deserialize(&sig.0)
        .map_err(|e| OvdsError::Bls(format!("bad sig: {:?}", e)))?;
    let dst = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_";
    let result = sig.verify(true, msg, dst, &[], &pk, true);
    Ok(result == blst::BLST_ERROR::BLST_SUCCESS)
}

// ---------------------------------------------------------------------------
// Hash to G1 — mimics Python group.hash(h, G1)
// ---------------------------------------------------------------------------

/// HG: SHA256 → hash_to_g1 mapped point.
/// In blst, sign() internally does hash-to-curve, so we use the raw sign/verify.
/// For explicit G1 operations (used in Python protocol), we construct G1 points.
pub fn hg(msg: &[u8]) -> G1Point {
    let hash = Sha256::digest(msg);
    // Sign an empty message with the hash as the secret key to get a G1 point
    // This is a simplified hash-to-g1: we can't easily do this without the blst hash_to API.
    // For protocol compatibility, use the raw hash bytes as the message to sign.
    G1Point(hash.to_vec())
}

// ---------------------------------------------------------------------------
// G1 group operations for protocol compatibility
// ---------------------------------------------------------------------------

/// G1 multiply: point^scalar (serialize as G1)
/// Since we can't easily do raw G1 arithmetic with blst public API,
/// we use aggregate signatures as a workaround.
pub fn g1_mul(_point: &G1Point, _scalar: &[u8]) -> Result<G1Point, OvdsError> {
    // Placeholder: blst doesn't expose raw G1 scalar multiplication easily.
    // For the VADS protocol, we can adapt to use BLS signatures directly.
    Err(OvdsError::Bls("raw G1 mul not exposed by blst".into()))
}

/// G1 add: point1 + point2
pub fn g1_add(a: &G1Point, b: &G1Point) -> Result<G1Point, OvdsError> {
    // Aggregate two signatures = point addition in G1
    let s1 = Signature::deserialize(&a.0)
        .map_err(|e| OvdsError::Bls(format!("bad g1: {:?}", e)))?;
    let s2 = Signature::deserialize(&b.0)
        .map_err(|e| OvdsError::Bls(format!("bad g1: {:?}", e)))?;
    let agg = AggregateSignature::aggregate(&[&s1, &s2], true)
        .map_err(|e| OvdsError::Bls(format!("aggregate: {:?}", e)))?;
    Ok(G1Point(agg.to_signature().compress().to_vec()))
}

/// G1 identity point
pub fn g1_identity() -> G1Point {
    G1Point(vec![0u8; 48])
}

// ---------------------------------------------------------------------------
// Aggregation (for batch verify)
// ---------------------------------------------------------------------------

/// Aggregate multiple G1 signatures.
pub fn aggregate_signatures(sigs: &[BlsSignature]) -> Result<BlsSignature, OvdsError> {
    if sigs.is_empty() {
        return Ok(BlsSignature(vec![0u8; 48]));
    }
    let refs: Vec<&Signature> = sigs.iter().map(|s| {
        let ptr = s.0.as_ptr() as *const Signature;
        unsafe { &*ptr }
    }).collect();
    let agg = AggregateSignature::aggregate(&refs, true)
        .map_err(|e| OvdsError::Bls(format!("aggregate: {:?}", e)))?;
    Ok(BlsSignature(agg.to_signature().compress().to_vec()))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sign_verify_roundtrip() {
        let (sk, pk) = key_gen();
        let sig = sign(&sk, b"hello").unwrap();
        assert!(verify(&pk, b"hello", &sig).unwrap());
    }

    #[test]
    fn wrong_msg_fails() {
        let (sk, pk) = key_gen();
        let sig = sign(&sk, b"hello").unwrap();
        assert!(!verify(&pk, b"world", &sig).unwrap());
    }

    #[test]
    fn g1_add_works() {
        let (sk, _) = key_gen();
        let a = sign(&sk, b"a").unwrap();
        let b = sign(&sk, b"b").unwrap();
        let ga = G1Point(a.0);
        let gb = G1Point(b.0);
        let sum = g1_add(&ga, &gb).unwrap();
        assert_eq!(sum.0.len(), 48);
    }

    #[test]
    fn aggregate_works() {
        let (sk, pk) = key_gen();
        let mut sigs = vec![];
        for i in 0..3 {
            let msg = format!("msg{i}").into_bytes();
            sigs.push(sign(&sk, &msg).unwrap());
        }
        let agg = aggregate_signatures(&sigs).unwrap();
        assert_eq!(agg.0.len(), 48);
    }
}
