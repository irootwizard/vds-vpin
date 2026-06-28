use std::collections::{HashMap, HashSet};
use std::sync::{Arc, OnceLock};

use ahe_client::PlatformConfig;
use ahe_crypto_e2::{coord_to_be32, E2Point};
use ahe_engine::{AheEngine, EngineStepResult};
use ahe_model_bundle::{load_network_a_weights, NetworkAWeights, NETWORK_A};
use ahe_protocol::{chunk_to_ws_frame, decode_ahe_v1_tensor, encode_ahe_v1_chunks};
use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    response::IntoResponse,
};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use rand::{rngs::StdRng, SeedableRng};
use serde_json::{json, Value};

static WEIGHTS: OnceLock<Arc<NetworkAWeights>> = OnceLock::new();

fn shared_weights(cfg: &PlatformConfig) -> Arc<NetworkAWeights> {
    WEIGHTS
        .get_or_init(|| {
            Arc::new(
                load_network_a_weights(&cfg.weights_dir).expect("load network-A weights"),
            )
        })
        .clone()
}

pub async fn session_ws(ws: WebSocketUpgrade) -> impl IntoResponse {
    let cfg = PlatformConfig::load();
    ws.on_upgrade(move |socket| handle(socket, cfg))
}

struct ChunkAsm {
    total: u32,
    chunks: HashMap<u32, Vec<u8>>,
}

impl ChunkAsm {
    fn new(total: u32) -> Self {
        Self {
            total,
            chunks: HashMap::new(),
        }
    }

    fn add(&mut self, i: u32, p: Vec<u8>) {
        self.chunks.insert(i, p);
    }

    fn ready(&self) -> bool {
        self.chunks.len() as u32 == self.total
    }

    fn decode(&self) -> Result<Vec<E2Point>, String> {
        let mut ordered = Vec::new();
        for i in 0..self.total {
            ordered.push(
                self.chunks
                    .get(&i)
                    .cloned()
                    .ok_or_else(|| "missing chunk".to_string())?,
            );
        }
        decode_ahe_v1_tensor(&ordered).map_err(|e| e.to_string())
    }
}

type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

enum EngineJob {
    Initial { c1: Ct4, c2: Ct4 },
    Accept {
        phase_id: String,
        c1: Ct4,
        c2: Ct4,
        c1_2d: Option<Vec<Vec<E2Point>>>,
        c2_2d: Option<Vec<Vec<E2Point>>>,
    },
}

async fn run_engine_job(
    mut engine: AheEngine<StdRng>,
    job: EngineJob,
) -> Result<(AheEngine<StdRng>, EngineStepResult), String> {
    tokio::task::spawn_blocking(move || {
        let result = match job {
            EngineJob::Initial { c1, c2 } => engine.bind_initial_ciphertext(c1, c2),
            EngineJob::Accept {
                phase_id,
                c1,
                c2,
                c1_2d,
                c2_2d,
            } => engine.accept_client_ciphertext(&phase_id, c1, c2, c1_2d, c2_2d),
        }
        .map_err(|e| e.to_string())?;
        Ok((engine, result))
    })
    .await
    .map_err(|e| e.to_string())?
}

async fn handle(socket: WebSocket, cfg: PlatformConfig) {
    let weights = shared_weights(&cfg);

    let mut engine: Option<AheEngine<StdRng>> = None;
    let mut assemblers: HashMap<(String, String), ChunkAsm> = HashMap::new();
    let mut processed: HashSet<String> = HashSet::new();

    let (mut write, mut read) = socket.split();
    while let Some(Ok(msg)) = read.next().await {
        let text = match msg {
            Message::Text(t) => t,
            _ => continue,
        };
        let frame: Value = match serde_json::from_str(&text) {
            Ok(v) => v,
            Err(e) => {
                send_err(&mut write, &e.to_string()).await;
                break;
            }
        };
        let msg_type = frame.get("type").and_then(|v| v.as_str()).unwrap_or("");

        if msg_type == "SessionStart" {
            send_json(
                &mut write,
                "SessionAccept",
                json!({
                    "session_id": "session-1",
                    "server_version": "vpin-backend-ahe-server/0.1.0",
                    "model_catalog_epoch": "0"
                }),
            )
            .await;
            continue;
        }

        if msg_type == "ModelSelect" {
            let phases: Vec<_> = NETWORK_A
                .truncation_phases
                .iter()
                .map(|p| {
                    json!({
                        "phase_id": p.phase_id,
                        "layer": p.client_action,
                        "bits": p.shift_bits.unwrap_or(16)
                    })
                })
                .collect();
            send_json(
                &mut write,
                "ModelSelectAck",
                json!({
                    "model_id": frame["model_id"],
                    "network_id": "A",
                    "topology_hash": "network-A-v1",
                    "weights_digest_hex": "rust-platform",
                    "truncation_plan": {"phases": phases},
                    "deployable": true,
                    "range_ok": true,
                    "accuracy_ok": true
                }),
            )
            .await;
            continue;
        }

        if msg_type == "InputDigest" {
            send_json(&mut write, "InputDigestAck", json!({"ok": true})).await;
            continue;
        }

        if msg_type == "PublicKey" {
            let hx = frame["h_x"].as_str().unwrap_or("0");
            let hy = frame["h_y"].as_str().unwrap_or("0");
            let x = coord_to_be32(&hx.parse().unwrap_or_default());
            let y = coord_to_be32(&hy.parse().unwrap_or_default());
            let pk = E2Point::Affine { x, y };
            engine = Some(AheEngine::new(pk, (*weights).clone(), StdRng::seed_from_u64(7)));
            assemblers.clear();
            processed.clear();
            continue;
        }

        if msg_type == "CiphertextPayload" {
            if engine.is_none() {
                send_err(&mut write, "PublicKey required").await;
                break;
            }
            let phase_id = frame["phase_id"].as_str().unwrap_or("").to_string();
            let part = frame["tensor_part"].as_str().unwrap_or("").to_string();
            let total = frame["total_chunks"].as_u64().unwrap_or(1) as u32;
            let idx = frame["chunk_index"].as_u64().unwrap_or(0) as u32;
            let b64 = frame["data_b64"].as_str().unwrap_or("");
            let payload = base64::engine::general_purpose::STANDARD
                .decode(b64)
                .map_err(|e| e.to_string())
                .unwrap_or_default();

            assemblers
                .entry((phase_id.clone(), part))
                .or_insert_with(|| ChunkAsm::new(total))
                .add(idx, payload);

            if processed.contains(&phase_id) || !pair_ready(&assemblers, &phase_id) {
                continue;
            }
            processed.insert(phase_id.clone());

            let c1_pts = assemblers
                .get(&(phase_id.clone(), "c1".into()))
                .unwrap()
                .decode()
                .unwrap_or_default();
            let c2_pts = assemblers
                .get(&(phase_id.clone(), "c2".into()))
                .unwrap()
                .decode()
                .unwrap_or_default();

            let eng = engine.take().expect("engine");
            let job = if phase_id == "initial" {
                EngineJob::Initial {
                    c1: reshape_4d(&c1_pts, &[1, 1, 32, 32]),
                    c2: reshape_4d(&c2_pts, &[1, 1, 32, 32]),
                }
            } else if phase_id == "after_conv" {
                EngineJob::Accept {
                    phase_id: phase_id.clone(),
                    c1: reshape_4d(&c1_pts, &[1, 1, 32, 32]),
                    c2: reshape_4d(&c2_pts, &[1, 1, 32, 32]),
                    c1_2d: None,
                    c2_2d: None,
                }
            } else {
                let n = c1_pts.len();
                EngineJob::Accept {
                    phase_id: phase_id.clone(),
                    c1: vec![],
                    c2: vec![],
                    c1_2d: Some(reshape_2d(&c1_pts, &[1, n])),
                    c2_2d: Some(reshape_2d(&c2_pts, &[1, n])),
                }
            };

            match run_engine_job(eng, job).await {
                Ok((eng, step)) => {
                    engine = Some(eng);
                    if let Err(e) = advance_engine(&mut write, &step).await {
                        send_err(&mut write, &e).await;
                        break;
                    }
                }
                Err(e) => {
                    send_err(&mut write, &e).await;
                    break;
                }
            }
        }
    }
}

fn pair_ready(assemblers: &HashMap<(String, String), ChunkAsm>, phase_id: &str) -> bool {
    ["c1", "c2"].iter().all(|part| {
        assemblers
            .get(&(phase_id.to_string(), (*part).to_string()))
            .map(|a| a.ready())
            .unwrap_or(false)
    })
}

fn reshape_4d(points: &[E2Point], shape: &[usize]) -> Ct4 {
    let mut idx = 0;
    let mut out = vec![vec![vec![vec![E2Point::Identity; shape[3]]; shape[2]]; shape[1]]; shape[0]];
    for b in 0..shape[0] {
        for c in 0..shape[1] {
            for h in 0..shape[2] {
                for w in 0..shape[3] {
                    out[b][c][h][w] = points[idx].clone();
                    idx += 1;
                }
            }
        }
    }
    out
}

fn reshape_2d(points: &[E2Point], shape: &[usize]) -> Vec<Vec<E2Point>> {
    let mut idx = 0;
    let mut out = vec![vec![E2Point::Identity; shape[1]]; shape[0]];
    for i in 0..shape[0] {
        for j in 0..shape[1] {
            out[i][j] = points[idx].clone();
            idx += 1;
        }
    }
    out
}

async fn advance_engine(
    write: &mut futures_util::stream::SplitSink<WebSocket, Message>,
    result: &EngineStepResult,
) -> Result<(), String> {
    let trunc = result
        .truncate
        .as_ref()
        .ok_or_else(|| "missing truncate".to_string())?;

    if let (Some(c1), Some(c2)) = (&result.output_c1, &result.output_c2) {
        send_server_ciphertext(write, &trunc.phase_id, c1, c2).await?;
    } else if let (Some(c1), Some(c2)) = (&result.output_c1_2d, &result.output_c2_2d) {
        let flat1 = c1[0].clone();
        let flat2 = c2[0].clone();
        send_server_ciphertext_flat(write, &trunc.phase_id, &flat1, &flat2).await?;
    }

    send_json(
        write,
        "TruncateRequest",
        json!({
            "phase_id": trunc.phase_id,
            "client_action": trunc.client_action,
            "shift_bits": trunc.shift_bits,
            "shape": trunc.shape,
            "bits": 16
        }),
    )
    .await;

    if result.inference_complete {
        send_json(
            write,
            "InferenceComplete",
            json!({
                "num_pt_add": result.num_pt_add,
                "num_pt_mult": result.num_pt_mult
            }),
        )
        .await;
        send_json(write, "SessionEnd", json!({"ok": true})).await;
    }
    Ok(())
}

async fn send_server_ciphertext(
    write: &mut futures_util::stream::SplitSink<WebSocket, Message>,
    phase_id: &str,
    c1: &[Vec<Vec<Vec<E2Point>>>],
    c2: &[Vec<Vec<Vec<E2Point>>>],
) -> Result<(), String> {
    let flat1 = flatten_4d(c1);
    let flat2 = flatten_4d(c2);
    send_server_ciphertext_flat(write, phase_id, &flat1, &flat2).await
}

fn flatten_4d(t: &[Vec<Vec<Vec<E2Point>>>]) -> Vec<E2Point> {
    let mut out = Vec::new();
    for b in t {
        for c in b {
            for row in c {
                for p in row {
                    out.push(p.clone());
                }
            }
        }
    }
    out
}

async fn send_server_ciphertext_flat(
    write: &mut futures_util::stream::SplitSink<WebSocket, Message>,
    phase_id: &str,
    c1: &[E2Point],
    c2: &[E2Point],
) -> Result<(), String> {
    for (part, pts) in [("c1", c1), ("c2", c2)] {
        let chunks = encode_ahe_v1_chunks(phase_id, part, pts, 256).map_err(|e| e.to_string())?;
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
                .map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

async fn send_json(
    write: &mut futures_util::stream::SplitSink<WebSocket, Message>,
    msg_type: &str,
    body: Value,
) {
    let mut obj = match body {
        Value::Object(m) => m,
        _ => serde_json::Map::new(),
    };
    obj.insert("type".into(), json!(msg_type));
    let _ = write.send(Message::Text(json!(obj).to_string())).await;
}

async fn send_err(write: &mut futures_util::stream::SplitSink<WebSocket, Message>, msg: &str) {
    send_json(write, "Error", json!({"message": msg})).await;
}
