use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WsMessage {
    SessionStart {
        client_version: String,
    },
    SessionAccept {
        session_id: String,
    },
    ModelSelect {
        model_id: String,
    },
    ModelSelectAck {
        model_id: String,
        network_id: String,
        truncation_plan: Vec<TruncationPlanItem>,
    },
    InputDigest {
        digest_hex: String,
    },
    InputDigestAck,
    PublicKey {
        h_x: String,
        h_y: String,
    },
    CiphertextChunk {
        phase_id: String,
        part: String,
        chunk_index: u32,
        total_chunks: u32,
        encoding: String,
        payload_b64: String,
    },
    TruncateRequest {
        phase_id: String,
        client_action: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        shift_bits: Option<u32>,
        shape: Vec<usize>,
    },
    InferenceComplete {
        num_pt_add: u64,
        num_pt_mult: u64,
    },
    SessionEnd,
    Error {
        message: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TruncationPlanItem {
    pub phase_id: String,
    pub client_action: String,
    pub shift_bits: Option<u32>,
    pub shape: Vec<usize>,
}
