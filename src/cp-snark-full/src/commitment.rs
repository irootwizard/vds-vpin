//! Pedersen-style commitments for model weights and public inputs.
//!
//! Prefer importing via [`crate::commit`]; this module remains for backward compatibility.
//!
//! Paper Setup: server commits to model W before inference; client receives cm_W.
//! We use Ristretto255 (E1) with embedded weight scalars mod q_1.

use curve25519_dalek::constants::RISTRETTO_BASEPOINT_POINT;
use curve25519_dalek::ristretto::{CompressedRistretto, RistrettoPoint};
use libspartan::scalar::Scalar;
use merlin::Transcript;
use rand::rngs::OsRng;
use rand::RngCore;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::curve::{embed_u128_to_scalar, CurveE2Params};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PedersenCommitment {
    /// Compressed Ristretto commitment point.
    pub point_hex: String,
    /// Blake-style digest binding the committed scalars (verifier checks consistency).
    pub digest_hex: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelCommitmentBundle {
    pub cm_weights: PedersenCommitment,
    pub num_weights: usize,
    /// E2-side digest of raw weights (AHE field binding).
    pub e2_digest_hex: String,
    pub curve_e2: CurveE2Params,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InputCommitmentBundle {
    pub cm_public: PedersenCommitment,
    /// Number of public input scalars in the sub-circuits.
    pub num_public_inputs: usize,
}

/// Plaintext opening for cross-process Pedersen verification (MVP; production may use NIZK).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModelCommitmentOpening {
    /// Committed weights as decimal `u128` strings (same order as `commit_model` input).
    pub weights: Vec<String>,
    pub blind_hex: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InputCommitmentOpening {
    /// Spartan scalar bytes (hex) for each public input scalar.
    pub public_scalars_hex: Vec<String>,
    pub blind_hex: String,
}

fn scalars_digest(scalars: &[Scalar]) -> String {
    let mut hasher = Sha256::new();
    for s in scalars {
        hasher.update(s.to_bytes());
    }
    hex::encode(hasher.finalize())
}

fn hash_to_generator_scalar(label: &[u8], index: usize) -> Scalar {
    let mut h = Sha256::new();
    h.update(label);
    h.update((index as u64).to_le_bytes());
    let gen_bytes = h.finalize();
    let mut wide = [0u8; 64];
    wide[..32].copy_from_slice(&gen_bytes);
    Scalar::from_bytes_wide(&wide)
}

fn recompute_pedersen_point(
    scalars: &[Scalar],
    blind: &Scalar,
    gen_label: &[u8],
) -> RistrettoPoint {
    let mut acc = blind * RISTRETTO_BASEPOINT_POINT;
    for (i, s) in scalars.iter().enumerate() {
        let gen_scalar = hash_to_generator_scalar(gen_label, i);
        acc += gen_scalar * (*s) * RISTRETTO_BASEPOINT_POINT;
    }
    acc
}

fn e2_weights_digest(weights: &[u128], curve: &CurveE2Params) -> String {
    let mut hasher = Sha256::new();
    hasher.update(curve.curve_order.as_bytes());
    for w in weights {
        hasher.update(w.to_le_bytes());
    }
    hex::encode(hasher.finalize())
}

/// Server-side: commit to model weights W.
pub fn commit_model(weights: &[u128]) -> (ModelCommitmentBundle, Vec<Scalar>, Scalar) {
    let curve_e2 = CurveE2Params::vpin_default();
    let scalars: Vec<Scalar> = weights.iter().copied().map(embed_u128_to_scalar).collect();
    let blind = {
        let mut wide = [0u8; 64];
        OsRng.fill_bytes(&mut wide[..32]);
        Scalar::from_bytes_wide(&wide)
    };

    let acc = recompute_pedersen_point(&scalars, &blind, b"cp-snark-model-gen");

    let cm = PedersenCommitment {
        point_hex: hex::encode(acc.compress().as_bytes()),
        digest_hex: scalars_digest(&scalars),
    };

    let bundle = ModelCommitmentBundle {
        cm_weights: cm,
        num_weights: weights.len(),
        e2_digest_hex: e2_weights_digest(weights, &curve_e2),
        curve_e2,
    };

    (bundle, scalars, blind)
}

/// Client-side: commit to public inputs (curve parameter a for point-mult sub-circuit).
pub fn commit_public_inputs(public_scalars: &[Scalar]) -> (InputCommitmentBundle, Scalar) {
    let blind = {
        let mut wide = [0u8; 64];
        OsRng.fill_bytes(&mut wide[..32]);
        Scalar::from_bytes_wide(&wide)
    };

    let acc = recompute_pedersen_point(public_scalars, &blind, b"cp-snark-input-gen");

    let cm = PedersenCommitment {
        point_hex: hex::encode(acc.compress().as_bytes()),
        digest_hex: scalars_digest(public_scalars),
    };

    let bundle = InputCommitmentBundle {
        cm_public: cm,
        num_public_inputs: public_scalars.len(),
    };

    (bundle, blind)
}

/// Build opening bundle for artifacts (prover → verifier over TLS).
pub fn model_opening_from_commit(
    weights: &[u128],
    blind: &Scalar,
) -> ModelCommitmentOpening {
    ModelCommitmentOpening {
        weights: weights.iter().map(|w| w.to_string()).collect(),
        blind_hex: hex::encode(blind.to_bytes()),
    }
}

pub fn input_opening_from_commit(
    public_scalars: &[Scalar],
    blind: &Scalar,
) -> InputCommitmentOpening {
    InputCommitmentOpening {
        public_scalars_hex: public_scalars
            .iter()
            .map(|s| hex::encode(s.to_bytes()))
            .collect(),
        blind_hex: hex::encode(blind.to_bytes()),
    }
}

pub fn opening_weights_to_scalars(opening: &ModelCommitmentOpening) -> Result<Vec<Scalar>, String> {
    opening
        .weights
        .iter()
        .map(|s| {
            let w: u128 = s
                .parse()
                .map_err(|e| format!("weight parse {s}: {e}"))?;
            Ok(embed_u128_to_scalar(w))
        })
        .collect()
}

pub fn opening_public_scalars(opening: &InputCommitmentOpening) -> Result<Vec<Scalar>, String> {
    opening
        .public_scalars_hex
        .iter()
        .map(|h| {
            let bytes = hex::decode(h).map_err(|e| format!("scalar hex: {e}"))?;
            if bytes.len() != 32 {
                return Err(format!("expected 32 bytes, got {}", bytes.len()));
            }
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&bytes);
            let ct = Scalar::from_bytes(&arr);
            if bool::from(ct.is_some()) {
                Ok(ct.unwrap())
            } else {
                Err("invalid scalar bytes".to_string())
            }
        })
        .collect()
}

fn parse_blind_hex(blind_hex: &str) -> Result<Scalar, String> {
    let bytes = hex::decode(blind_hex).map_err(|e| format!("blind hex: {e}"))?;
    if bytes.len() != 32 {
        return Err(format!("blind: expected 32 bytes, got {}", bytes.len()));
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    let ct = Scalar::from_bytes(&arr);
    if bool::from(ct.is_some()) {
        Ok(ct.unwrap())
    } else {
        Err("invalid blind scalar".to_string())
    }
}

/// Verify Pedersen point opening for $\mathsf{cm}_W$.
pub fn verify_pedersen_open_model(
    model: &ModelCommitmentBundle,
    opening: &ModelCommitmentOpening,
) -> bool {
    let scalars = match opening_weights_to_scalars(opening) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let blind = match parse_blind_hex(&opening.blind_hex) {
        Ok(b) => b,
        Err(_) => return false,
    };
    if !verify_model_commitment(model, &scalars) {
        return false;
    }
    let expected = recompute_pedersen_point(&scalars, &blind, b"cp-snark-model-gen");
    let Some(compressed) = decompress_commitment(&model.cm_weights.point_hex) else {
        return false;
    };
    let Some(opened) = compressed.decompress() else {
        return false;
    };
    expected == opened
}

/// Verify Pedersen point opening for $\mathsf{cm}_x$.
pub fn verify_pedersen_open_input(
    input: &InputCommitmentBundle,
    opening: &InputCommitmentOpening,
) -> bool {
    let scalars = match opening_public_scalars(opening) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let blind = match parse_blind_hex(&opening.blind_hex) {
        Ok(b) => b,
        Err(_) => return false,
    };
    if !verify_input_commitment(input, &scalars) {
        return false;
    }
    let expected = recompute_pedersen_point(&scalars, &blind, b"cp-snark-input-gen");
    let Some(compressed) = decompress_commitment(&input.cm_public.point_hex) else {
        return false;
    };
    let Some(opened) = compressed.decompress() else {
        return false;
    };
    expected == opened
}

pub fn append_commitments_to_transcript(
    transcript: &mut Transcript,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
) {
    transcript.append_message(b"cp_snark_protocol", b"vPIN_cp_snark_full_v1");
    transcript.append_message(b"cm_model_point", model.cm_weights.point_hex.as_bytes());
    transcript.append_message(b"cm_model_digest", model.cm_weights.digest_hex.as_bytes());
    transcript.append_message(b"cm_model_e2_digest", model.e2_digest_hex.as_bytes());
    transcript.append_message(b"cm_input_point", input.cm_public.point_hex.as_bytes());
    transcript.append_message(b"cm_input_digest", input.cm_public.digest_hex.as_bytes());
}

pub fn decompress_commitment(hex_str: &str) -> Option<CompressedRistretto> {
    let bytes = hex::decode(hex_str).ok()?;
    if bytes.len() != 32 {
        return None;
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    Some(CompressedRistretto(arr))
}

/// Verifier checks that the prover's weight digest matches the published commitment.
pub fn verify_model_commitment(model: &ModelCommitmentBundle, weight_scalars: &[Scalar]) -> bool {
    model.num_weights == weight_scalars.len()
        && model.cm_weights.digest_hex == scalars_digest(weight_scalars)
}

pub fn verify_input_commitment(input: &InputCommitmentBundle, public_scalars: &[Scalar]) -> bool {
    input.num_public_inputs == public_scalars.len()
        && input.cm_public.digest_hex == scalars_digest(public_scalars)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pedersen_model_open_roundtrip() {
        let weights = vec![1u128, 2, 3, 42];
        let (bundle, scalars, blind) = commit_model(&weights);
        let opening = model_opening_from_commit(&weights, &blind);
        assert!(verify_pedersen_open_model(&bundle, &opening));
        assert!(verify_model_commitment(&bundle, &scalars));
    }

    #[test]
    fn pedersen_input_open_roundtrip() {
        let public = vec![Scalar::from(7u64), Scalar::from(11u64)];
        let (bundle, blind) = commit_public_inputs(&public);
        let opening = input_opening_from_commit(&public, &blind);
        assert!(verify_pedersen_open_input(&bundle, &opening));
    }
}
