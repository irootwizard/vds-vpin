use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use ahe_codec::{
    apply_client_action, apply_relu_pool_shift, decrypt_tensor, encrypt_tensor,
    fixed_point_to_real, ClientAction, BsgsTable,
};
use ahe_crypto_e2::{be32_to_coord, E2Point, KeyMaterial};
use ahe_protocol::{chunk_to_ws_frame, decode_ahe_v1_tensor, encode_ahe_v1_chunks};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use rand::{rngs::StdRng, SeedableRng};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use thiserror::Error;
use tokio_tungstenite::{connect_async, tungstenite::Message};

#[derive(Clone, Debug, Default)]
pub struct AheTiming {
    pub preprocess_ms: f64,
    pub encrypt_ms: f64,
    pub decrypt_ms: f64,
    /// Client-side encrypt + decrypt only.
    pub client_crypto_ms: f64,
    /// Wall time waiting on server homomorphic steps (total - client_crypto - ws).
    pub server_wait_ms: f64,
    /// Alias for server_wait_ms (legacy field name).
    pub network_ms: f64,
    pub ws_ms: f64,
    /// Full session wall clock — matches Python `crypto_infer_ms` semantics.
    pub crypto_infer_ms: f64,
    pub total_ms: f64,
}

struct SessionProfiler {
    encrypt_ms: f64,
    decrypt_ms: f64,
    ws_ms: f64,
}

impl SessionProfiler {
    fn new() -> Self {
        Self {
            encrypt_ms: 0.0,
            decrypt_ms: 0.0,
            ws_ms: 0.0,
        }
    }

    fn finish(self, total_ms: f64) -> AheTiming {
        let client_crypto = self.encrypt_ms + self.decrypt_ms;
        let server_wait = (total_ms - client_crypto - self.ws_ms).max(0.0);
        AheTiming {
            preprocess_ms: 0.0,
            encrypt_ms: self.encrypt_ms,
            decrypt_ms: self.decrypt_ms,
            client_crypto_ms: client_crypto,
            server_wait_ms: server_wait,
            network_ms: server_wait,
            ws_ms: self.ws_ms,
            crypto_infer_ms: total_ms,
            total_ms,
        }
    }
}

#[derive(Clone, Debug)]
pub struct AheSessionResult {
    pub prediction: i32,
    pub logits: Vec<f32>,
    pub label: Option<i32>,
    pub mnist_index: Option<i32>,
    pub input_digest_hex: String,
    pub timing: AheTiming,
    pub num_pt_add: u64,
    pub num_pt_mult: u64,
}

#[derive(Error, Debug)]
pub enum SessionError {
    #[error("ws: {0}")]
    Ws(String),
    #[error("protocol: {0}")]
    Protocol(String),
    #[error("crypto: {0}")]
    Crypto(String),
}

struct ChunkAssembler {
    total: u32,
    chunks: HashMap<u32, Vec<u8>>,
}

impl ChunkAssembler {
    fn new(total: u32) -> Self {
        Self {
            total,
            chunks: HashMap::new(),
        }
    }

    fn add(&mut self, idx: u32, payload: Vec<u8>) {
        self.chunks.insert(idx, payload);
    }

    fn ready(&self) -> bool {
        self.chunks.len() as u32 == self.total
    }

    fn decode(&self) -> Result<Vec<E2Point>, SessionError> {
        let mut ordered = Vec::new();
        for i in 0..self.total {
            ordered.push(
                self.chunks
                    .get(&i)
                    .cloned()
                    .ok_or_else(|| SessionError::Protocol("missing chunk".into()))?,
            );
        }
        decode_ahe_v1_tensor(&ordered).map_err(|e| SessionError::Protocol(e.to_string()))
    }
}

fn digest_hex(fixed: &[i32]) -> String {
    let mut bytes = Vec::new();
    for &v in fixed {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    format!("{:x}", Sha256::digest(&bytes))
}

fn pubkey_coords(pk: &E2Point) -> (String, String) {
    match pk {
        E2Point::Identity => ("0".into(), "0".into()),
        E2Point::Affine { x, y } => (
            be32_to_coord(x).to_string(),
            be32_to_coord(y).to_string(),
        ),
    }
}

pub async fn run_ahe_session(
    backend_ws: &str,
    model_id: &str,
    fixed_int32: &[i32],
    shape: &[usize],
    bsgs: &Arc<BsgsTable>,
    keys: Option<KeyMaterial>,
    mnist_index: Option<i32>,
    label: Option<i32>,
) -> Result<AheSessionResult, SessionError> {
    let t0 = Instant::now();
    let keys = keys.unwrap_or_else(|| {
        let mut krng = StdRng::seed_from_u64(42);
        KeyMaterial::key_gen(&mut krng)
    });
    let digest = digest_hex(fixed_int32);

    let (ws, _) = connect_async(backend_ws)
        .await
        .map_err(|e| SessionError::Ws(e.to_string()))?;
    let (mut write, mut read) = ws.split();

    let mut assemblers: HashMap<(String, String), ChunkAssembler> = HashMap::new();
    let mut pending_truncate: Option<Value> = None;
    let mut prediction = -1i32;
    let mut logits: Vec<f32> = Vec::new();
    let mut num_pt_add = 0u64;
    let mut num_pt_mult = 0u64;
    let mut done = false;
    let mut profiler = SessionProfiler::new();

    async fn send_json(
        write: &mut futures_util::stream::SplitSink<
            tokio_tungstenite::WebSocketStream<
                tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
            >,
            Message,
        >,
        v: Value,
    ) -> Result<(), SessionError> {
        write
            .send(Message::Text(v.to_string()))
            .await
            .map_err(|e| SessionError::Ws(e.to_string()))
    }

    async fn send_ciphertext(
        write: &mut futures_util::stream::SplitSink<
            tokio_tungstenite::WebSocketStream<
                tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
            >,
            Message,
        >,
        phase_id: &str,
        points_c1: &[E2Point],
        points_c2: &[E2Point],
    ) -> Result<(), SessionError> {
        for (part, pts) in [("c1", points_c1), ("c2", points_c2)] {
            let chunks = encode_ahe_v1_chunks(phase_id, part, pts, 256)
                .map_err(|e| SessionError::Protocol(e.to_string()))?;
            for ch in chunks {
                let mut frame = chunk_to_ws_frame(&ch);
                if let Some(obj) = frame.as_object_mut() {
                    obj.insert("type".into(), json!("CiphertextPayload"));
                    obj.insert("tensor_part".into(), json!(part));
                    let payload = obj.remove("payload_b64").unwrap();
                    obj.insert("data_b64".into(), payload);
                }
                send_json(write, frame).await?;
            }
        }
        Ok(())
    }

    send_json(
        &mut write,
        json!({
            "type": "SessionStart",
            "client_version": "vpin-client/0.1.0",
            "ahe_params_id": "e2-default"
        }),
    )
    .await?;
    send_json(&mut write, json!({"type": "ModelSelect", "model_id": model_id})).await?;
    send_json(
        &mut write,
        json!({
            "type": "InputDigest",
            "input_digest_hex": digest,
            "shape": shape,
            "fixed_point_bits": 16,
            "mnist_index": mnist_index,
        }),
    )
    .await?;
    let (hx, hy) = pubkey_coords(&keys.public_key);
    send_json(
        &mut write,
        json!({"type": "PublicKey", "h_x": hx, "h_y": hy}),
    )
    .await?;

    let t_enc = Instant::now();
    let keys_enc = keys.clone();
    let plain_init: Vec<i32> = fixed_int32.to_vec();
    let (enc_c1, enc_c2) = tokio::task::spawn_blocking(move || {
        let mut local = StdRng::seed_from_u64(42);
        encrypt_tensor(&plain_init, &keys_enc, &mut local)
    })
    .await
    .map_err(|e| SessionError::Crypto(e.to_string()))?;
    profiler.encrypt_ms += t_enc.elapsed().as_secs_f64() * 1000.0;
    let t_ws = Instant::now();
    send_ciphertext(&mut write, "initial", &enc_c1, &enc_c2).await?;
    profiler.ws_ms += t_ws.elapsed().as_secs_f64() * 1000.0;

    while !done {
        let msg = read
            .next()
            .await
            .ok_or_else(|| SessionError::Ws("closed".into()))?
            .map_err(|e| SessionError::Ws(e.to_string()))?;
        let frame: Value = match msg {
            Message::Text(t) => {
                serde_json::from_str(&t).map_err(|e| SessionError::Protocol(e.to_string()))?
            }
            _ => continue,
        };
        let msg_type = frame
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        if msg_type == "CiphertextPayload" {
            let phase_id = frame["phase_id"].as_str().unwrap_or("").to_string();
            let part = frame["tensor_part"].as_str().unwrap_or("").to_string();
            let total = frame["total_chunks"].as_u64().unwrap_or(1) as u32;
            let idx = frame["chunk_index"].as_u64().unwrap_or(0) as u32;
            let b64 = frame["data_b64"].as_str().unwrap_or("");
            let payload = base64::engine::general_purpose::STANDARD
                .decode(b64)
                .map_err(|e| SessionError::Protocol(e.to_string()))?;
            let key = (phase_id.clone(), part.clone());
            assemblers
                .entry(key)
                .or_insert_with(|| ChunkAssembler::new(total))
                .add(idx, payload);
            if let Some(tr) = pending_truncate.clone() {
                let pid = tr["phase_id"].as_str().unwrap_or("");
                if pair_ready(&assemblers, pid) {
                    handle_truncate(
                        &mut write,
                        &mut assemblers,
                        &tr,
                        &keys,
                        bsgs,
                        &mut prediction,
                        &mut logits,
                        &mut profiler,
                    )
                    .await?;
                    pending_truncate = None;
                }
            }
        } else if msg_type == "TruncateRequest" {
            let pid = frame["phase_id"].as_str().unwrap_or("");
            if pair_ready(&assemblers, pid) {
                handle_truncate(
                    &mut write,
                    &mut assemblers,
                    &frame,
                    &keys,
                    bsgs,
                    &mut prediction,
                    &mut logits,
                    &mut profiler,
                )
                .await?;
            } else {
                pending_truncate = Some(frame);
            }
        } else if msg_type == "InferenceComplete" {
            num_pt_add = frame["num_pt_add"].as_u64().unwrap_or(0);
            num_pt_mult = frame["num_pt_mult"].as_u64().unwrap_or(0);
        } else if msg_type == "SessionEnd" {
            done = true;
        } else if msg_type == "Error" {
            return Err(SessionError::Protocol(
                frame["message"].as_str().unwrap_or("error").into(),
            ));
        }
    }

    let total_ms = t0.elapsed().as_secs_f64() * 1000.0;
    Ok(AheSessionResult {
        prediction,
        logits,
        label,
        mnist_index,
        input_digest_hex: digest,
        timing: profiler.finish(total_ms),
        num_pt_add,
        num_pt_mult,
    })
}

fn pair_ready(assemblers: &HashMap<(String, String), ChunkAssembler>, phase_id: &str) -> bool {
    for part in ["c1", "c2"] {
        let key = (phase_id.to_string(), part.to_string());
        match assemblers.get(&key) {
            Some(a) if a.ready() => {}
            _ => return false,
        }
    }
    true
}

async fn handle_truncate(
    write: &mut futures_util::stream::SplitSink<
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        Message,
    >,
    assemblers: &mut HashMap<(String, String), ChunkAssembler>,
    frame: &Value,
    keys: &KeyMaterial,
    bsgs: &Arc<BsgsTable>,
    prediction: &mut i32,
    logits: &mut Vec<f32>,
    profiler: &mut SessionProfiler,
) -> Result<(), SessionError> {
    let phase_id = frame["phase_id"].as_str().unwrap_or("");
    let action_s = frame["client_action"].as_str().unwrap_or("relu");
    let shift_bits = frame["shift_bits"].as_u64().map(|v| v as u32);
    let c1 = assemblers
        .get(&(phase_id.to_string(), "c1".into()))
        .unwrap()
        .decode()?;
    let c2 = assemblers
        .get(&(phase_id.to_string(), "c2".into()))
        .unwrap()
        .decode()?;
    let t_dec = Instant::now();
    let keys_dec = keys.clone();
    let bsgs_dec = Arc::clone(bsgs);
    let dec = tokio::task::spawn_blocking(move || {
        decrypt_tensor(&keys_dec, &c1, &c2, &bsgs_dec).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| SessionError::Crypto(e.to_string()))?
    .map_err(SessionError::Crypto)?;
    profiler.decrypt_ms += t_dec.elapsed().as_secs_f64() * 1000.0;
    let action = ClientAction::parse(action_s)
        .ok_or_else(|| SessionError::Protocol(format!("unknown action {action_s}")))?;

    // Terminal actions: extract logits and done (no re-encryption).
    if matches!(action, ClientAction::ReluOnly | ClientAction::LogitsOnly) {
        let out = apply_client_action(&dec, action, shift_bits).map_err(SessionError::Crypto)?;
        // ReluOnly (Network A): output was historically interpreted at f=16 (preserve behaviour).
        // LogitsOnly (LeNet): fc5 output is at f=32 (float weights × f=16 input).
        let logit_scale = if matches!(action, ClientAction::LogitsOnly) { 32 } else { 16 };
        *logits = fixed_point_to_real(&out, logit_scale);
        *prediction = out
            .iter()
            .enumerate()
            .max_by_key(|(_, v)| *v)
            .map(|(i, _)| i as i32)
            .unwrap_or(0);
        return Ok(());
    }

    // LeNet conv phases: relu + client-side avg pool + shift.
    let processed = if matches!(action, ClientAction::ReluPoolShift) {
        let pool_kernel = frame["pool_kernel"].as_u64().unwrap_or(2) as usize;
        let input_shape: Vec<usize> = frame["input_shape"]
            .as_array()
            .map(|arr| arr.iter().filter_map(|v| v.as_u64().map(|n| n as usize)).collect())
            .unwrap_or_default();
        let bits = shift_bits.ok_or_else(|| SessionError::Protocol("shift_bits required for relu_pool_shift".into()))?;
        apply_relu_pool_shift(&dec, &input_shape, pool_kernel, bits)
            .map_err(SessionError::Crypto)?
    } else {
        apply_client_action(&dec, action, shift_bits).map_err(SessionError::Crypto)?
    };
    let plain: Vec<i32> = processed.iter().map(|&v| v as i32).collect();
    let t_enc = Instant::now();
    let keys_enc = keys.clone();
    let (enc_c1, enc_c2) = tokio::task::spawn_blocking(move || {
        let mut local = rand::thread_rng();
        encrypt_tensor(&plain, &keys_enc, &mut local)
    })
    .await
    .map_err(|e| SessionError::Crypto(e.to_string()))?;
    profiler.encrypt_ms += t_enc.elapsed().as_secs_f64() * 1000.0;

    let t_ws = Instant::now();
    for (part, pts) in [("c1", &enc_c1), ("c2", &enc_c2)] {
        let chunks = encode_ahe_v1_chunks(phase_id, part, pts, 256)
            .map_err(|e| SessionError::Protocol(e.to_string()))?;
        for ch in chunks {
            let mut frame = chunk_to_ws_frame(&ch);
            if let Some(obj) = frame.as_object_mut() {
                obj.insert("type".into(), json!("CiphertextPayload"));
                obj.insert("tensor_part".into(), json!(part));
                let payload = obj.remove("payload_b64").unwrap();
                obj.insert("data_b64".into(), payload);
            }
            write
                .send(Message::Text(frame.to_string()))
                .await
                .map_err(|e| SessionError::Ws(e.to_string()))?;
        }
    }
    profiler.ws_ms += t_ws.elapsed().as_secs_f64() * 1000.0;
    Ok(())
}

pub type SharedBsgsTable = Arc<BsgsTable>;

pub fn load_bsgs(path: &std::path::Path) -> Result<SharedBsgsTable, SessionError> {
    if path.extension().and_then(|s| s.to_str()) == Some("bin") {
        BsgsTable::load(path)
            .map(Arc::new)
            .map_err(|e| SessionError::Crypto(e.to_string()))
    } else {
        Err(SessionError::Crypto(
            "use table.bin; run tools/bsgs-convert".into(),
        ))
    }
}

