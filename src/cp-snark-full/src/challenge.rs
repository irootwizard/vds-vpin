//! Client random challenge for CP-SNARK (paper § RLC / soundness).
//!
//! **Design:** `docs/cp-snark-分层证明与RLC设计定稿.md`
//! - Compliance: client samples γ/γ′ **before** prove (P4); binds transcript.
//! - **Not** the same as `Server.py` `pf(secret_key,i)` (server debug self-check on path [A]).
//! - Eq.(9)(10) **computation** is already in `rLCL`/`rLCR`; this module is for **verifier** randomness.
//!
//! Field usage (wired in `layer_proof::common::challenge_for_stage`):
//! - `gamma` → convolution RLC (paper Eq. 9)
//! - `gamma_add` → average pooling / point-add batch
//! - `gamma_mult` → FC RLC γ′ (paper Eq. 10)

use libspartan::scalar::Scalar;
use libspartan::transcript::AppendToTranscript;
use merlin::Transcript;
use rand::rngs::OsRng;
use rand::RngCore;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ClientChallenge {
    /// Global challenge scalar (analogous to γ in paper RLC).
    pub gamma: String,
    /// Per-gadget challenges for point-add / point-mult batches.
    pub gamma_add: String,
    pub gamma_mult: String,
    /// Number of point additions and multiplications covered.
    pub num_point_adds: usize,
    pub num_point_mults: usize,
}

impl ClientChallenge {
    pub fn sample(num_point_adds: usize, num_point_mults: usize) -> Self {
        Self {
            gamma: random_scalar_hex(),
            gamma_add: random_scalar_hex(),
            gamma_mult: random_scalar_hex(),
            num_point_adds,
            num_point_mults,
        }
    }

    pub fn gamma_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma)
    }

    pub fn gamma_add_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma_add)
    }

    pub fn gamma_mult_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma_mult)
    }
}

fn random_scalar_hex() -> String {
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    hex::encode(bytes)
}

fn hex_to_scalar(h: &str) -> Scalar {
    let bytes = hex::decode(h).unwrap_or_else(|_| vec![0u8; 32]);
    let mut wide = [0u8; 64];
    let len = bytes.len().min(64);
    wide[..len].copy_from_slice(&bytes[..len]);
    Scalar::from_bytes_wide(&wide)
}

pub fn append_challenge_to_transcript(transcript: &mut Transcript, challenge: &ClientChallenge) {
    challenge
        .gamma_scalar()
        .append_to_transcript(b"client_gamma", transcript);
    challenge
        .gamma_add_scalar()
        .append_to_transcript(b"client_gamma_add", transcript);
    challenge
        .gamma_mult_scalar()
        .append_to_transcript(b"client_gamma_mult", transcript);
    transcript.append_message(
        b"challenge_counts",
        format!(
            "{}:{}",
            challenge.num_point_adds, challenge.num_point_mults
        )
        .as_bytes(),
    );
}

/// Random linear combination check: γ * left + (1-γ) * right binding (simplified RLC).
pub fn rlc_bind_scalars(left: Scalar, right: Scalar, challenge: &ClientChallenge) -> Scalar {
    let g = challenge.gamma_scalar();
    g * left + (Scalar::one() - g) * right
}
