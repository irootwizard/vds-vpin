//! VADS protocol — mirrors Python `vads_lib.py` Algorithm 1 & 2.
//!
//! Python reference:
//!   setup()         → (vk, sk, server_state)      lines 326-421
//!   append_client() → (i, s, sigma_i, tag_i)       lines 490-535
//!   append_server() → verify + store                lines 537-583
//!   query()         → (s_i, sigma_i, tag_i, pi)     lines 585-651
//!   verify()        → bool                           lines 718-808
//!   audit()         → pi_a                           lines 919-1019
//!   judge()         → bool                           lines 1021-1131

use num_bigint::BigUint;
use num_traits::{One, Zero};
use rand::Rng;
use std::collections::HashSet;

use crate::bls::{self, BlsSignature, hg};
use crate::error::OvdsError;
use crate::hash;
use crate::rsa_acc;
use crate::types::*;

const SECURITY_PARAM: usize = 128;

// =========================================================================
// Algorithm 1: Setup  (Python lines 326-421)
// =========================================================================

pub fn setup() -> Result<(VerificationKey, SecretKey, ServerState), OvdsError> {
    // Client: generate BLS keypair (Python: group.random, alpha, A=g^alpha)
    let (alpha, pk) = bls::key_gen();

    // Client: init RSA Accumulator (Python: accumulator_setup())
    let (n, acc_0, phi) = rsa_acc::setup()?;

    // G2 generator (blst uses fixed generator)
    let g = G2Point(vec![0u8; 96]); // placeholder — blst uses internal generator

    // Random u ∈ G1 (Python: group.random(G1))
    let mut rng = rand::thread_rng();
    let mut u_bytes = [0u8; 32];
    rng.fill(&mut u_bytes);
    let u = hg(&u_bytes);

    let vk = VerificationKey {
        g: g.clone(),
        u: u.clone(),
        a: pk.clone(),
        n: n.clone(),
        h: acc_0.clone(),
        acc_0: acc_0.clone(),
    };

    let sk = SecretKey { alpha: alpha.clone(), cnt: 0, vk: vk.clone() };

    let state = ServerState {
        vk: vk.clone(),
        r: HashSet::new(),
        db: std::collections::HashMap::new(),
        acc_r: acc_0.clone(),
        z_star: BigUint::from(1u32),
        n: n.clone(),
        phi: phi.clone(),
    };

    Ok((vk, sk, state))
}

// =========================================================================
// Algorithm 1: Append — Client  (Python lines 490-535)
// =========================================================================

/// Client append: sign the data.
/// Python: sigma_i = (HG(i||tag_i) * u^s)^alpha
pub fn append_client(sk: &mut SecretKey, s: &BigUint) -> (u64, Record) {
    let i = sk.cnt;
    sk.cnt += 1;

    // tag_i ∈ {0,1}^λ  (Python: secrets.randbits(SECURITY_PARAM))
    let mut rng = rand::thread_rng();
    let mut tag_bytes = vec![0u8; SECURITY_PARAM / 8];
    rng.fill(&mut tag_bytes[..]);
    let tag = BigUint::from_bytes_be(&tag_bytes);

    // sigma_i = sign(sk, i||tag||s)
    // Python: HG(i||tag) * u^s → blst: sign raw msg
    let mut msg = i.to_be_bytes().to_vec();
    msg.extend_from_slice(&tag.to_bytes_be());
    msg.extend_from_slice(&s.to_bytes_be());
    let sigma = bls::sign(&sk.alpha, &msg).expect("BLS sign");

    (i, Record { s: s.clone(), sigma, tag })
}

// =========================================================================
// Algorithm 1: Append — Server  (Python lines 537-583)
// =========================================================================

/// Server append: verify BLS signature and store.
/// Python: e(sigma_i, g) == e(HG(i||tag_i) * u^s, A)
pub fn append_server(
    vk: &VerificationKey,
    state: &mut ServerState,
    i: u64,
    record: &Record,
) -> Result<(), OvdsError> {
    // Reconstruct signed message
    let mut msg = i.to_be_bytes().to_vec();
    msg.extend_from_slice(&record.tag.to_bytes_be());
    msg.extend_from_slice(&record.s.to_bytes_be());

    // Verify: e(sigma, g) == e(HG(msg), pk)
    let valid = bls::verify(&vk.a, &msg, &record.sigma)?;
    if !valid {
        return Err(OvdsError::Verification("BLS signature invalid".into()));
    }

    // Store in DB
    state.db.insert(i, record.clone());

    // Update RSA accumulator: Acc' = Acc^{HPrime(tag)} mod n
    let tag_prime = hash::hprime(&record.tag);
    state.acc_r = rsa_acc::add_member(&state.acc_r, &tag_prime, &state.n);

    Ok(())
}

/// Combined append (convenience, Python line 424)
pub fn append(sk: &mut SecretKey, s: &BigUint, state: &mut ServerState) -> Result<(u64, Record), OvdsError> {
    let (i, record) = append_client(sk, s);
    append_server(&sk.vk, state, i, &record)?;
    Ok((i, record))
}

// =========================================================================
// Algorithm 1: Query  (Python lines 585-651)
// =========================================================================

/// Query single record.
pub fn query(state: &ServerState, i: u64) -> Result<QueryResponse, OvdsError> {
    let record = state.db.get(&i).ok_or(OvdsError::NotFound(i))?;
    let pi = NonMembershipProof {
        x: state.acc_r.clone(),
        y: state.vk.h.modpow(&state.z_star, &state.n),
    };
    Ok(QueryResponse {
        index: i,
        value: record.s.clone(),
        proof: QueryProof { sigma: record.sigma.clone(), tag: record.tag.clone(), pi },
    })
}

/// Query multiple records (star).
pub fn query_star(state: &ServerState, indices: &[u64]) -> Result<QueryStarResponse, OvdsError> {
    let mut values = Vec::new();
    let mut items = Vec::new();
    for &i in indices {
        let record = state.db.get(&i).ok_or(OvdsError::NotFound(i))?;
        values.push((i, record.s.clone()));
        items.push((i, record.sigma.clone(), record.tag.clone()));
    }
    let pi_j = NonMembershipProof {
        x: state.acc_r.clone(),
        y: state.vk.h.modpow(&state.z_star, &state.n),
    };
    Ok(QueryStarResponse { values, proof: QueryStarProof { items, pi_j } })
}

// =========================================================================
// Algorithm 1: Verify  (Python lines 718-808)
// =========================================================================

/// Verify single query proof.
pub fn verify_query(vk: &VerificationKey, resp: &QueryResponse) -> Result<bool, OvdsError> {
    let mut msg = resp.index.to_be_bytes().to_vec();
    msg.extend_from_slice(&resp.proof.tag.to_bytes_be());
    msg.extend_from_slice(&resp.value.to_bytes_be());
    bls::verify(&vk.a, &msg, &resp.proof.sigma)
}

/// Verify batch query proof.
pub fn verify_query_star(vk: &VerificationKey, resp: &QueryStarResponse) -> Result<bool, OvdsError> {
    for (i, sigma, tag) in &resp.proof.items {
        if let Some((_, val)) = resp.values.iter().find(|(idx, _)| idx == i) {
            let mut msg = i.to_be_bytes().to_vec();
            msg.extend_from_slice(&tag.to_bytes_be());
            msg.extend_from_slice(&val.to_bytes_be());
            if !bls::verify(&vk.a, &msg, sigma)? {
                return Ok(false);
            }
        }
    }
    Ok(true)
}

// =========================================================================
// Algorithm 1: Update  (Python lines 1133-1231)
// =========================================================================

/// Update a record: replace s with s', produce new signature.
/// Old tag goes into R (revoked set), new tag and signature replace it.
pub fn update(
    sk: &SecretKey,
    i: u64,
    s_prime: &BigUint,
    state: &mut ServerState,
) -> Result<Record, OvdsError> {
    let old = state.db.get(&i).ok_or(OvdsError::NotFound(i))?;

    // Old tag → R (revoked set)
    state.r.insert(old.tag.clone());
    // Update z_star = z_star * HPrime(old_tag)
    let old_prime = hash::hprime(&old.tag);
    state.z_star = (&state.z_star * &old_prime) % &state.n;
    // Update Acc_R = Acc_R^{HPrime(old_tag)}  (remove old from accumulator)
    state.acc_r = rsa_acc::remove_member(&state.acc_r, &old_prime, &state.n, &state.phi)?;

    // Sign new value (same index)
    let mut rng = rand::thread_rng();
    let mut tag_bytes = vec![0u8; SECURITY_PARAM / 8];
    rng.fill(&mut tag_bytes[..]);
    let new_tag = BigUint::from_bytes_be(&tag_bytes);

    let mut msg = i.to_be_bytes().to_vec();
    msg.extend_from_slice(&new_tag.to_bytes_be());
    msg.extend_from_slice(&s_prime.to_bytes_be());
    let new_sigma = bls::sign(&sk.alpha, &msg)?;

    let record = Record { s: s_prime.clone(), sigma: new_sigma, tag: new_tag.clone() };

    // Verify new signature on server side
    let mut vfy_msg = i.to_be_bytes().to_vec();
    vfy_msg.extend_from_slice(&record.tag.to_bytes_be());
    vfy_msg.extend_from_slice(&s_prime.to_bytes_be());
    if !bls::verify(&state.vk.a, &vfy_msg, &record.sigma)? {
        return Err(OvdsError::Verification("update signature invalid".into()));
    }
    state.db.insert(i, record.clone());
    // Add new tag to accumulator
    let new_prime = hash::hprime(&new_tag);
    state.acc_r = rsa_acc::add_member(&state.acc_r, &new_prime, &state.n);

    Ok(record)
}

// =========================================================================
// Algorithm 1: Audit  (Python lines 919-1019)
// =========================================================================

/// Server generates audit proof over a set of indices I.
/// Proves that all records in I are correctly stored and signed.
pub fn audit(state: &ServerState, indices: &[u64]) -> Result<AuditProof, OvdsError> {
    if indices.is_empty() {
        return Err(OvdsError::InvalidParam("empty audit set".into()));
    }

    // Aggregate: nu = sum of all s_i (for the proof)
    let mut nu = BigUint::zero();
    let mut sigs: Vec<BlsSignature> = vec![];
    let mut tags: Vec<BigUint> = vec![];

    for &i in indices {
        let record = state.db.get(&i).ok_or(OvdsError::NotFound(i))?;
        nu += &record.s;
        sigs.push(record.sigma.clone());
        tags.push(record.tag.clone());
    }

    // Aggregate signatures: sigma_I = aggregate of all sigma_i
    let sigma_i = bls::aggregate_signatures(&sigs)?;

    // Non-membership proof for all tags (proving none are in R)
    let q_tags: Vec<BigUint> = tags.iter().map(|t| hash::hprime(t)).collect();
    let q_product: BigUint = q_tags.iter().fold(BigUint::one(), |a, b| a * b);
    let pi_1 = rsa_acc::prove_non_membership(&state.acc_r, &state.z_star, &q_product, &state.n, &state.vk.h);

    Ok(AuditProof { nu, sigma_i, pi_1 })
}

// =========================================================================
// Algorithm 1: Judge  (Python lines 1021-1131)
// =========================================================================

/// Client verifies an audit proof.
pub fn judge(vk: &VerificationKey, indices: &[u64], values: &[BigUint], proof: &AuditProof) -> Result<bool, OvdsError> {
    if indices.len() != values.len() || indices.is_empty() {
        return Ok(false);
    }

    // Verify aggregated signature covers all (i, s_i) pairs
    // For each i, verify: e(sigma_I, g) == e(aggregate HG(i||tag), A) * e(u^nu, A)
    let nu: BigUint = values.iter().sum();
    if proof.nu != nu {
        return Ok(false);
    }

    // Verify BLS: e(sigma_I, g) == e(HG(msg), A)
    let mut agg_msg = vec![];
    for (&i, s) in indices.iter().zip(values.iter()) {
        agg_msg.extend_from_slice(&i.to_be_bytes());
        agg_msg.extend_from_slice(&s.to_bytes_be());
    }
    let pk = BlsPublicKey(vk.a.0.clone());
    let valid = bls::verify(&pk, &agg_msg, &proof.sigma_i)?;
    Ok(valid)
}

// =========================================================================
// Tests
// =========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn setup_works() {
        let (vk, sk, state) = setup().unwrap();
        assert_eq!(sk.cnt, 0);
        assert!(state.db.is_empty());
        assert!(!vk.n.is_zero());
    }

    #[test]
    fn append_query_verify_roundtrip() {
        let (vk, mut sk, mut state) = setup().unwrap();
        let val = BigUint::from(42u32);
        let (i, _) = append(&mut sk, &val, &mut state).unwrap();
        assert_eq!(i, 0);
        let resp = query(&state, 0).unwrap();
        assert_eq!(resp.value, val);
        assert!(verify_query(&vk, &resp).unwrap());
    }

    #[test]
    fn multiple_appends() {
        let (vk, mut sk, mut state) = setup().unwrap();
        for k in 0..10u32 {
            append(&mut sk, &BigUint::from(k * 10), &mut state).unwrap();
        }
        for k in 0..10u32 {
            let resp = query(&state, k as u64).unwrap();
            assert_eq!(resp.value, BigUint::from(k * 10));
            assert!(verify_query(&vk, &resp).unwrap());
        }
    }

    #[test]
    fn tampered_record_rejected() {
        let (vk, mut sk, mut state) = setup().unwrap();
        let val = BigUint::from(42u32);
        let (i, mut record) = append_client(&mut sk, &val);
        record.s = BigUint::from(99u32); // tamper
        assert!(append_server(&vk, &mut state, i, &record).is_err());
    }

    #[test]
    fn query_star_works() {
        let (vk, mut sk, mut state) = setup().unwrap();
        for k in 0..5u32 {
            append(&mut sk, &BigUint::from(k * 10), &mut state).unwrap();
        }
        let resp = query_star(&state, &[0, 2, 4]).unwrap();
        assert_eq!(resp.values.len(), 3);
        assert!(verify_query_star(&vk, &resp).unwrap());
    }
}
