use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use ahe_codec::apply_relu_pool_shift;
use ahe_codec_ec::{
    apply_client_action, ark_to_ec, decrypt_tensor, ec_to_ark, encrypt_tensor,
    fixed_point_to_real, ClientAction, BsgsTable, EcE2Point, EcKeyMaterial,
};
use ahe_crypto_e2::E2Point;
use ahe_crypto_e2_ec::be32_to_coord;
use ahe_protocol::{chunk_to_ws_frame, decode_ahe_v1_tensor, encode_ahe_v1_chunks};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use num_bigint::BigUint;
use rand::{rngs::StdRng, SeedableRng};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio_tungstenite::{connect_async, tungstenite::Message};

use crate::trace::{emit_progress, make_trace_step, phase_meta, ProgressCb};

use crate::session::{AheSessionResult, AheTiming, SessionError};

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

    fn decode(&self) -> Result<Vec<EcE2Point>, SessionError> {
        let mut ordered = Vec::new();
        for i in 0..self.total {
            ordered.push(
                self.chunks
                    .get(&i)
                    .cloned()
                    .ok_or_else(|| SessionError::Protocol("missing chunk".into()))?,
            );
        }
        decode_ahe_v1_tensor(&ordered)
            .map(|pts| pts.iter().map(ark_to_ec).collect())
            .map_err(|e| SessionError::Protocol(e.to_string()))
    }
}

fn ec_points_to_wire(points: &[EcE2Point]) -> Vec<E2Point> {
    points.iter().map(ec_to_ark).collect()
}

fn digest_hex(fixed: &[i32]) -> String {
    let mut bytes = Vec::new();
    for &v in fixed {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    format!("{:x}", Sha256::digest(&bytes))
}

fn pubkey_coords(pk: &EcE2Point) -> (String, String) {
    match pk {
        EcE2Point::Identity => ("0".into(), "0".into()),
        EcE2Point::Affine { x, y, .. } => (
            be32_to_coord(x).to_string(),
            be32_to_coord(y).to_string(),
        ),
    }
}

pub async fn run_ahe_session_ec(
    backend_ws: &str,
    model_id: &str,
    fixed_int32: &[i32],
    shape: &[usize],
    bsgs: &Arc<BsgsTable>,
    keys: Option<EcKeyMaterial>,
    mnist_index: Option<i32>,
    label: Option<i32>,
    on_progress: Option<ProgressCb>,
) -> Result<AheSessionResult, SessionError> {
    let t0 = Instant::now();
    let keys = keys.unwrap_or_else(|| EcKeyMaterial::key_gen_deterministic(BigUint::from(42u32)));
    let digest = digest_hex(fixed_int32);

    let (ws, _) = connect_async(backend_ws)
        .await
        .map_err(|e| SessionError::Ws(e.to_string()))?;
    let (mut write, mut read) = ws.split();

    emit_progress(
        &on_progress,
        json!({"kind":"progress","phase":"session_start","backend":backend_ws,"engine":"rust-ec"}),
    );

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
        points_c1: &[EcE2Point],
        points_c2: &[EcE2Point],
    ) -> Result<(), SessionError> {
        for (part, pts) in [("c1", points_c1), ("c2", points_c2)] {
            let wire_pts = ec_points_to_wire(pts);
            let chunks = encode_ahe_v1_chunks(phase_id, part, &wire_pts, 256)
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
                        keys.clone(),
                        Arc::clone(bsgs),
                        &mut prediction,
                        &mut logits,
                        &mut profiler,
                        &on_progress,
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
                    keys.clone(),
                    Arc::clone(bsgs),
                    &mut prediction,
                    &mut logits,
                    &mut profiler,
                    &on_progress,
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
    keys: EcKeyMaterial,
    bsgs: Arc<BsgsTable>,
    prediction: &mut i32,
    logits: &mut Vec<f32>,
    profiler: &mut SessionProfiler,
    on_progress: &Option<ProgressCb>,
) -> Result<(), SessionError> {
    let phase_id = frame["phase_id"].as_str().unwrap_or("");
    let action_s = frame["client_action"].as_str().unwrap_or("relu");
    let shift_bits = frame["shift_bits"].as_u64().map(|v| v as u32);
    let (layer, client_op) = phase_meta(phase_id);
    emit_progress(
        on_progress,
        json!({
            "kind": "progress",
            "phase": "trace",
            "step": make_trace_step(
                &format!("server_ct_{phase_id}"),
                "\u{670d}\u{52a1}\u{7aef}",
                &format!("{layer} · 服务端密文输出"),
                &format!("phase={phase_id}"),
                json!({"phase_id":phase_id,"layer":layer,"data_form":"ElGamal ciphertext (EC)"}),
            ),
        }),
    );
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
    let bsgs_dec = Arc::clone(&bsgs);
    let dec = tokio::task::spawn_blocking(move || {
        let n = c1.len();
        let result = decrypt_tensor(&keys_dec, &c1, &c2, &bsgs_dec);
        eprintln!("[session_ec] decrypted {n} values, err={}", result.is_err());
        if let Ok(ref vals) = result {
            let max_abs = vals.iter().map(|v| v.abs()).max().unwrap_or(0);
            let preview: Vec<i64> = vals.iter().take(5).copied().collect();
            eprintln!("[session_ec] range: first5={preview:?} max_abs={max_abs}");
        }
        result.map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| SessionError::Crypto(e.to_string()))?
    .map_err(SessionError::Crypto)?;
    profiler.decrypt_ms += t_dec.elapsed().as_secs_f64() * 1000.0;
    emit_progress(
        on_progress,
        json!({
            "kind": "progress",
            "phase": "trace",
            "step": make_trace_step(
                &format!("client_decrypt_{phase_id}"),
                "\u{5ba2}\u{6237}\u{7aef}",
                &format!("{layer} · 客户端解密"),
                &format!("action={action_s}"),
                json!({"phase_id":phase_id,"client_action":action_s,"shift_bits":shift_bits,"operation":client_op}),
            ),
        }),
    );
    let action = ClientAction::parse(action_s)
        .ok_or_else(|| SessionError::Protocol(format!("unknown action {action_s}")))?;
    if matches!(action, ClientAction::ReluOnly | ClientAction::LogitsOnly) {
        let out = apply_client_action(&dec, action, shift_bits).map_err(SessionError::Crypto)?;
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
    let processed = if matches!(action, ClientAction::ReluPoolShift) {
        let pool_kernel = frame["pool_kernel"].as_u64().unwrap_or(2) as usize;
        let input_shape: Vec<usize> = frame["input_shape"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_u64().map(|n| n as usize))
                    .collect()
            })
            .unwrap_or_default();
        let bits = shift_bits.ok_or_else(|| {
            SessionError::Protocol("shift_bits required for relu_pool_shift".into())
        })?;
        apply_relu_pool_shift(&dec, &input_shape, pool_kernel, bits)
            .map_err(SessionError::Crypto)?
    } else {
        let result = apply_client_action(&dec, action, shift_bits).map_err(SessionError::Crypto)?;
        eprintln!("[session_ec] apply_client_action ok, len={}, first5={:?}, max_abs={}",
            result.len(),
            &result[..result.len().min(5)],
            result.iter().map(|v| v.abs()).max().unwrap_or(0));
        result
    };
    let plain: Vec<i32> = processed.iter().map(|&v| v as i32).collect();
    eprintln!("[session_ec] plain i32: len={}, first5={:?}, max_abs={}",
        plain.len(), &plain[..plain.len().min(5)], plain.iter().map(|v| v.abs()).max().unwrap_or(0));
    let t_enc = Instant::now();
    let keys_enc = keys.clone();
    let (enc_c1, enc_c2) = tokio::task::spawn_blocking(move || {
        let mut local = rand::thread_rng();
        encrypt_tensor(&plain, &keys_enc, &mut local)
    })
    .await
    .map_err(|e| SessionError::Crypto(e.to_string()))?;
    eprintln!("[session_ec] encrypt_tensor ok, n={}", enc_c1.len());
    profiler.encrypt_ms += t_enc.elapsed().as_secs_f64() * 1000.0;

    let t_ws = Instant::now();
    for (part, pts) in [("c1", &enc_c1), ("c2", &enc_c2)] {
        let wire_pts = ec_points_to_wire(pts);
        eprintln!("[session_ec] encoding {}: {} points", part, wire_pts.len());
        let chunks = encode_ahe_v1_chunks(phase_id, part, &wire_pts, 256)
            .map_err(|e| SessionError::Protocol(e.to_string()))?;
        eprintln!("[session_ec] {} chunks={} sending...", part, chunks.len());
        for (ci, ch) in chunks.iter().enumerate() {
            let mut frame = chunk_to_ws_frame(ch);
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
            if ci % 50 == 0 || ci == chunks.len() - 1 {
                eprintln!("[session_ec] {part} chunk {ci}/{} sent", chunks.len());
            }
        }
        eprintln!("[session_ec] {} all {} chunks sent", part, chunks.len());
    }
    profiler.ws_ms += t_ws.elapsed().as_secs_f64() * 1000.0;
    Ok(())
}

pub type SharedBsgsTableEc = Arc<BsgsTable>;

pub fn load_bsgs_ec(path: &std::path::Path) -> Result<SharedBsgsTableEc, SessionError> {
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

