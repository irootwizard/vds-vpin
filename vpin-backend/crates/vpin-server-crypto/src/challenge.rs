//! Client random challenge (P4). Server must not sample γ in production.

use libspartan::scalar::Scalar;
use libspartan::transcript::AppendToTranscript;
use merlin::Transcript;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ClientChallenge {
    pub gamma: String,
    pub gamma_add: String,
    pub gamma_mult: String,
    #[serde(alias = "num_pt_add")]
    pub num_point_adds: usize,
    #[serde(alias = "num_pt_mult")]
    pub num_point_mults: usize,
}

impl ClientChallenge {
    pub fn gamma_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma)
    }

    pub fn gamma_add_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma_add)
    }

    pub fn gamma_mult_scalar(&self) -> Scalar {
        hex_to_scalar(&self.gamma_mult)
    }

    /// True when all challenge scalars are present (non-empty hex).
    pub fn has_client_gamma(&self) -> bool {
        !self.gamma.is_empty() && !self.gamma_add.is_empty() && !self.gamma_mult.is_empty()
    }
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
