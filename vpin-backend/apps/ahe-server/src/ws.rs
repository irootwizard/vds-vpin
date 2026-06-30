use std::collections::{HashMap, HashSet};
use std::sync::{Arc, OnceLock};

use ahe_client::PlatformConfig;
use ahe_crypto_e2::{coord_to_be32, E2Point};
use ahe_engine::{AheEngine, AheLeNetEngine, EngineStepResult, LeNetStepResult};
use ahe_model_bundle::{
    load_lenet_cifar_weights, load_lenet_mnist_weights, load_network_a_weights, NetworkAWeights,
    LENET_CIFAR, LENET_MNIST, NETWORK_A, registry_model_info,
};
use ahe_protocol::{chunk_to_ws_frame, decode_ahe_v1_tensor, encode_ahe_v1_chunks};
use axum::{
    extract::ws::{Message, WebSocket, WebSocketUpgrade},
    response::IntoResponse,
};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use rand::{rngs::StdRng, SeedableRng};
use serde_json::{json, Value};

// ---------------------------------------------------------------------------
// Weight caches (each loaded once on first use)
// ---------------------------------------------------------------------------

static WEIGHTS_A: OnceLock<Arc<NetworkAWeights>> = OnceLock::new();
fn shared_weights_a(cfg: &PlatformConfig) -> Arc<NetworkAWeights> {
    WEIGHTS_A
        .get_or_init(|| {
            Arc::new(load_network_a_weights(&cfg.weights_dir).expect("load network-A weights"))
        })
        .clone()
}

// ---------------------------------------------------------------------------
// Public WebSocket entry point
// ---------------------------------------------------------------------------

pub async fn session_ws(ws: WebSocketUpgrade) -> impl IntoResponse {
    let cfg = PlatformConfig::load();
    ws.on_upgrade(move |socket| handle(socket, cfg))
}

// ---------------------------------------------------------------------------
// Session engine — wraps either the Network-A or LeNet engine
// ---------------------------------------------------------------------------

enum SessionEngine {
    NetworkA(AheEngine<StdRng>),
    LeNetMnist(AheLeNetEngine<StdRng>),
    LeNetCifar(AheLeNetEngine<StdRng>),
}

// ---------------------------------------------------------------------------
// Internal chunk assembler
// ---------------------------------------------------------------------------

struct ChunkAsm {
    total: u32,
    chunks: HashMap<u32, Vec<u8>>,
}

impl ChunkAsm {
    fn new(total: u32) -> Self {
        Self { total, chunks: HashMap::new() }
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

// ---------------------------------------------------------------------------
// Engine job dispatch
// ---------------------------------------------------------------------------

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

/// Unified result type carrying the fields both engines produce.
struct StepOut {
    phase_id: String,
    client_action: String,
    shift_bits: Option<u32>,
    shape: Vec<usize>,
    pool_kernel: Option<usize>,
    input_shape: Option<Vec<usize>>,
    output_c1: Option<Ct4>,
    output_c2: Option<Ct4>,
    output_c1_2d: Option<Vec<Vec<E2Point>>>,
    output_c2_2d: Option<Vec<Vec<E2Point>>>,
    inference_complete: bool,
    num_pt_add: u64,
    num_pt_mult: u64,
}

fn step_out_from_a(r: EngineStepResult) -> StepOut {
    let tr = r.truncate.as_ref().unwrap();
    StepOut {
        phase_id: tr.phase_id.clone(),
        client_action: tr.client_action.clone(),
        shift_bits: tr.shift_bits,
        shape: tr.shape.clone(),
        pool_kernel: None,
        input_shape: None,
        output_c1: r.output_c1,
        output_c2: r.output_c2,
        output_c1_2d: r.output_c1_2d,
        output_c2_2d: r.output_c2_2d,
        inference_complete: r.inference_complete,
        num_pt_add: r.num_pt_add,
        num_pt_mult: r.num_pt_mult,
    }
}

fn step_out_from_lenet(r: LeNetStepResult) -> StepOut {
    let tr = r.truncate.as_ref().unwrap();
    StepOut {
        phase_id: tr.phase_id.clone(),
        client_action: tr.client_action.clone(),
        shift_bits: tr.shift_bits,
        shape: tr.shape.clone(),
        pool_kernel: tr.pool_kernel,
        input_shape: tr.input_shape.clone(),
        output_c1: r.output_c1,
        output_c2: r.output_c2,
        output_c1_2d: r.output_c1_2d,
        output_c2_2d: r.output_c2_2d,
        inference_complete: r.inference_complete,
        num_pt_add: r.num_pt_add,
        num_pt_mult: r.num_pt_mult,
    }
}

async fn run_engine_job(
    mut engine: SessionEngine,
    job: EngineJob,
) -> Result<(SessionEngine, StepOut), String> {
    tokio::task::spawn_blocking(move || {
        let out = match &mut engine {
            SessionEngine::NetworkA(eng) => {
                let r = match job {
                    EngineJob::Initial { c1, c2 } => eng.bind_initial_ciphertext(c1, c2),
                    EngineJob::Accept { phase_id, c1, c2, c1_2d, c2_2d } => {
                        eng.accept_client_ciphertext(&phase_id, c1, c2, c1_2d, c2_2d)
                    }
                }
                .map_err(|e| e.to_string())?;
                step_out_from_a(r)
            }
            SessionEngine::LeNetMnist(eng) | SessionEngine::LeNetCifar(eng) => {
                let r = match job {
                    EngineJob::Initial { c1, c2 } => eng.bind_initial_ciphertext(c1, c2),
                    EngineJob::Accept { phase_id, c1, c2, c1_2d, c2_2d } => {
                        eng.accept_client_ciphertext(&phase_id, c1, c2, c1_2d, c2_2d)
                    }
                }
                .map_err(|e| e.to_string())?;
                step_out_from_lenet(r)
            }
        };
        Ok((engine, out))
    })
    .await
    .map_err(|e| e.to_string())?
}

// ---------------------------------------------------------------------------
// Main WebSocket handler
// ---------------------------------------------------------------------------

async fn handle(socket: WebSocket, cfg: PlatformConfig) {
    let mut engine: Option<SessionEngine> = None;
    let mut assemblers: HashMap<(String, String), ChunkAsm> = HashMap::new();
    let mut processed: HashSet<String> = HashSet::new();
    let mut selected_model_id = String::new();
    let mut selected_network_id = String::from("A");

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
            let model_id = frame["model_id"].as_str().unwrap_or("").to_string();
            // Determine network_id by prefix/suffix of model_id
            let (network_id, topology) = if model_id.contains("lenet") && model_id.contains("mnist") {
                ("lenet_mnist", LENET_MNIST)
            } else if model_id.contains("lenet") {
                ("lenet_cifar", LENET_CIFAR)
            } else {
                ("A", NETWORK_A)
            };

            selected_model_id = model_id.clone();
            selected_network_id = network_id.to_string();

            let phases: Vec<_> = topology
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
                    "model_id": model_id,
                    "network_id": network_id,
                    "topology_hash": format!("network-{}-v1", network_id),
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

            engine = Some(match selected_network_id.as_str() {
                "lenet_mnist" => {
                    // Load from registry-specified weights_dir
                    let dir = registry_model_info(&cfg.repo_root, &selected_model_id)
                        .map(|(d, _)| d)
                        .unwrap_or_else(|| cfg.repo_root.join("model_training/outputs/lenet_mnist"));
                    let w = load_lenet_mnist_weights(&dir)
                        .expect("load lenet-mnist weights");
                    SessionEngine::LeNetMnist(AheLeNetEngine::new_mnist(
                        pk, w, LENET_MNIST, StdRng::seed_from_u64(7),
                    ))
                }
                "lenet_cifar" => {
                    let dir = registry_model_info(&cfg.repo_root, &selected_model_id)
                        .map(|(d, _)| d)
                        .unwrap_or_else(|| cfg.weights_dir.clone());
                    let w = load_lenet_cifar_weights(&dir)
                        .expect("load lenet-cifar weights");
                    SessionEngine::LeNetCifar(AheLeNetEngine::new_cifar(
                        pk, w, LENET_CIFAR, StdRng::seed_from_u64(7),
                    ))
                }
                _ => {
                    let w = shared_weights_a(&cfg);
                    SessionEngine::NetworkA(AheEngine::new(
                        pk, (*w).clone(), StdRng::seed_from_u64(7),
                    ))
                }
            });
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
            let job = build_job(&phase_id, c1_pts, c2_pts, &selected_network_id);

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

/// Build the correct EngineJob given the phase_id and the current network type.
fn build_job(
    phase_id: &str,
    c1_pts: Vec<E2Point>,
    c2_pts: Vec<E2Point>,
    network_id: &str,
) -> EngineJob {
    match (phase_id, network_id) {
        // Network A: initial and after_conv are 4D [1,1,32,32]
        ("initial", "A") => EngineJob::Initial {
            c1: reshape_4d(&c1_pts, &[1, 1, 32, 32]),
            c2: reshape_4d(&c2_pts, &[1, 1, 32, 32]),
        },
        ("after_conv", "A") => EngineJob::Accept {
            phase_id: phase_id.to_string(),
            c1: reshape_4d(&c1_pts, &[1, 1, 32, 32]),
            c2: reshape_4d(&c2_pts, &[1, 1, 32, 32]),
            c1_2d: None,
            c2_2d: None,
        },

        // LeNet-MNIST initial: [1, 1, 32, 32]
        ("initial", "lenet_mnist") => EngineJob::Initial {
            c1: reshape_4d(&c1_pts, &[1, 1, 32, 32]),
            c2: reshape_4d(&c2_pts, &[1, 1, 32, 32]),
        },
        // LeNet-CIFAR initial: [1, 3, 32, 32]
        ("initial", "lenet_cifar") => EngineJob::Initial {
            c1: reshape_4d(&c1_pts, &[1, 3, 32, 32]),
            c2: reshape_4d(&c2_pts, &[1, 3, 32, 32]),
        },
        // after_conv1: client sends [1, 6, 14, 14] (after relu+pool+shift)
        ("after_conv1", "lenet_mnist" | "lenet_cifar") => EngineJob::Accept {
            phase_id: phase_id.to_string(),
            c1: reshape_4d(&c1_pts, &[1, 6, 14, 14]),
            c2: reshape_4d(&c2_pts, &[1, 6, 14, 14]),
            c1_2d: None,
            c2_2d: None,
        },
        // after_conv2: client sends [1, 16, 5, 5] (after relu+pool+shift)
        ("after_conv2", "lenet_mnist" | "lenet_cifar") => EngineJob::Accept {
            phase_id: phase_id.to_string(),
            c1: reshape_4d(&c1_pts, &[1, 16, 5, 5]),
            c2: reshape_4d(&c2_pts, &[1, 16, 5, 5]),
            c1_2d: None,
            c2_2d: None,
        },

        // All other phases (after_pool, after_fc1, after_fc2 for Network A;
        // after_c3, after_fc4 for LeNet) are flat 2D.
        _ => {
            let n = c1_pts.len();
            EngineJob::Accept {
                phase_id: phase_id.to_string(),
                c1: vec![],
                c2: vec![],
                c1_2d: Some(reshape_2d(&c1_pts, &[1, n])),
                c2_2d: Some(reshape_2d(&c2_pts, &[1, n])),
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

// ---------------------------------------------------------------------------
// Send helpers
// ---------------------------------------------------------------------------

async fn advance_engine(
    write: &mut futures_util::stream::SplitSink<WebSocket, Message>,
    step: &StepOut,
) -> Result<(), String> {
    if let (Some(c1), Some(c2)) = (&step.output_c1, &step.output_c2) {
        send_server_ciphertext(write, &step.phase_id, c1, c2).await?;
    } else if let (Some(c1), Some(c2)) = (&step.output_c1_2d, &step.output_c2_2d) {
        let flat1 = c1[0].clone();
        let flat2 = c2[0].clone();
        send_server_ciphertext_flat(write, &step.phase_id, &flat1, &flat2).await?;
    }

    // Build TruncateRequest — include pool fields when present (LeNet conv phases)
    let mut tr_body = json!({
        "phase_id": step.phase_id,
        "client_action": step.client_action,
        "shift_bits": step.shift_bits,
        "shape": step.shape,
        "bits": 16
    });
    if let Some(pk) = step.pool_kernel {
        tr_body["pool_kernel"] = json!(pk);
    }
    if let Some(ref is) = step.input_shape {
        tr_body["input_shape"] = json!(is);
    }
    send_json(write, "TruncateRequest", tr_body).await;

    if step.inference_complete {
        send_json(
            write,
            "InferenceComplete",
            json!({
                "num_pt_add": step.num_pt_add,
                "num_pt_mult": step.num_pt_mult
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
