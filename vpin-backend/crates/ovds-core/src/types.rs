use num_bigint::BigUint;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

pub use crate::bls::{BlsPublicKey, BlsSecretKey, BlsSignature, G1Point, G2Point};

/// Verification Key (mirrors Python vk dict)
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct VerificationKey {
    pub g: G2Point,          // G2 generator
    pub u: G1Point,          // random G1 element
    pub a: BlsPublicKey,     // A = g^alpha
    pub n: BigUint,          // RSA modulus
    pub h: BigUint,          // RSA accumulator base
    pub acc_0: BigUint,      // initial accumulator Acc(∅)
}

/// Secret Key (mirrors Python sk dict)
#[derive(Clone, Debug)]
pub struct SecretKey {
    pub alpha: BlsSecretKey,
    pub cnt: u64,
    pub vk: VerificationKey,
}

/// Database record
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Record {
    pub s: BigUint,
    pub sigma: BlsSignature,
    pub tag: BigUint,
}

/// Server state (mirrors Python server_state dict)
#[derive(Clone, Debug)]
pub struct ServerState {
    pub vk: VerificationKey,
    pub r: HashSet<BigUint>,
    pub db: HashMap<u64, Record>,
    pub acc_r: BigUint,
    pub z_star: BigUint,
    pub n: BigUint,
    /// RSA φ(n) = (p-1)(q-1) — server-only, for remove_member
    pub phi: BigUint,
}

/// RSA non-membership proof
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NonMembershipProof {
    pub x: BigUint,
    pub y: BigUint,
}

/// Query proof
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueryProof {
    pub sigma: BlsSignature,
    pub tag: BigUint,
    pub pi: NonMembershipProof,
}

/// Batch query proof
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueryStarProof {
    pub items: Vec<(u64, BlsSignature, BigUint)>,
    pub pi_j: NonMembershipProof,
}

/// Audit proof
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AuditProof {
    pub nu: BigUint,
    pub sigma_i: BlsSignature,
    pub pi_1: NonMembershipProof,
}

/// Query response
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueryResponse {
    pub index: u64,
    pub value: BigUint,
    pub proof: QueryProof,
}

/// Batch query response
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueryStarResponse {
    pub values: Vec<(u64, BigUint)>,
    pub proof: QueryStarProof,
}
