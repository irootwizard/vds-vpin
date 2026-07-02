//! Long-running stdin/stdout JSON worker for ResNet18 homomorphic inference.
//!
//! Protocol (one JSON object per line, newline-delimited):
//!
//!   Request:  {"cmd":"init","weights_dir":"...","pubkey_x":"hex","pubkey_y":"hex"}
//!   Response: {"ok":true}
//!
//!   Request:  {"cmd":"step","phase_id":"after_stem",...,
//!               "c1_xy":[[x_hex,y_hex],...],"c2_xy":[[x_hex,y_hex],...],
//!               "shape":[1,64,32,32]}
//!   Response: {"ok":true,"out_c1_xy":[[...],...],"out_c2_xy":[[...],...],
//!               "truncate":{...},"inference_complete":false,"add":N,"mult":N}
//!
//! E2Point wire format: "Identity" is null, affine is [x_hex, y_hex] where each is
//! a 64-char hex string (BE u256).  Python sends (int, int) decimal tuples which
//! are converted on the Rust side.

use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;

use ahe_crypto_e2::E2Point;
use ahe_engine::AheResNetEngine;
use ahe_model_bundle::load_resnet_weights;
use num_bigint::BigUint;
use rand::{rngs::StdRng, SeedableRng};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

#[derive(Deserialize)]
#[serde(tag = "cmd")]
enum Request {
    #[serde(rename = "init")]
    Init {
        weights_dir: String,
        pubkey_x: String,
        pubkey_y: String,
    },
    #[serde(rename = "step")]
    Step {
        phase_id: String,
        c1_xy: Vec<Option<(String, String)>>,
        c2_xy: Vec<Option<(String, String)>>,
        shape: Vec<usize>,
    },
}

#[derive(Serialize)]
struct OkResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    out_c1_xy: Option<Vec<Option<(String, String)>>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    out_c2_xy: Option<Vec<Option<(String, String)>>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    shape: Option<Vec<usize>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    truncate: Option<TruncateInfo>,
    #[serde(default)]
    inference_complete: bool,
    #[serde(default)]
    add: u64,
    #[serde(default)]
    mult: u64,
}

#[derive(Serialize)]
struct TruncateInfo {
    phase_id: String,
    client_action: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    shift_bits: Option<u32>,
    shape: Vec<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pool_kernel: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    input_shape: Option<Vec<usize>>,
}

fn parse_hex_or_decimal(s: &str) -> BigUint {
    if let Some(stripped) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        BigUint::parse_bytes(stripped.as_bytes(), 16).unwrap_or_default()
    } else {
        BigUint::parse_bytes(s.as_bytes(), 10).unwrap_or_default()
    }
}

fn parse_point(p: &Option<(String, String)>) -> E2Point {
    match p {
        None => E2Point::Identity,
        Some((x_str, y_str)) => {
            let x = parse_hex_or_decimal(x_str);
            let y = parse_hex_or_decimal(y_str);
            let mut x_bytes = x.to_bytes_be();
            let mut y_bytes = y.to_bytes_be();
            if x_bytes.len() > 32 {
                x_bytes = x_bytes[x_bytes.len() - 32..].to_vec();
            }
            if y_bytes.len() > 32 {
                y_bytes = y_bytes[y_bytes.len() - 32..].to_vec();
            }
            let mut x_arr = [0u8; 32];
            let mut y_arr = [0u8; 32];
            let x_off = 32 - x_bytes.len();
            let y_off = 32 - y_bytes.len();
            x_arr[x_off..].copy_from_slice(&x_bytes);
            y_arr[y_off..].copy_from_slice(&y_bytes);
            E2Point::Affine { x: x_arr, y: y_arr }
        }
    }
}

fn point_to_xy(p: &E2Point) -> Option<(String, String)> {
    match p {
        E2Point::Identity => None,
        E2Point::Affine { x, y } => {
            let x_u = BigUint::from_bytes_be(x);
            let y_u = BigUint::from_bytes_be(y);
            Some((x_u.to_str_radix(10), y_u.to_str_radix(10)))
        }
    }
}

fn reshape_flat(flat: Vec<E2Point>, shape: &[usize]) -> Ct4 {
    assert!(shape.len() == 4, "shape must be 4-D for Ct4");
    let mut it = flat.into_iter();
    let mut out = Vec::with_capacity(shape[0]);
    for _b in 0..shape[0] {
        let mut batch = Vec::with_capacity(shape[1]);
        for _c in 0..shape[1] {
            let mut ch = Vec::with_capacity(shape[2]);
            for _h in 0..shape[2] {
                let mut row = Vec::with_capacity(shape[3]);
                for _w in 0..shape[3] {
                    row.push(it.next().unwrap_or(E2Point::Identity));
                }
                ch.push(row);
            }
            batch.push(ch);
        }
        out.push(batch);
    }
    out
}

fn flatten_ct4(ct: &Ct4) -> Vec<E2Point> {
    let mut flat = Vec::new();
    for b in ct {
        for c in b {
            for h in c {
                for w in h {
                    flat.push(w.clone());
                }
            }
        }
    }
    flat
}

fn emit_ok(rsp: &OkResponse) {
    let line = serde_json::to_string(rsp).unwrap();
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    writeln!(handle, "{}", line).unwrap();
    handle.flush().unwrap();
}

fn emit_error(msg: &str) {
    let mut map = Map::new();
    map.insert("ok".into(), Value::Bool(false));
    map.insert("error".into(), Value::String(msg.to_string()));
    let line = serde_json::to_string(&Value::Object(map)).unwrap();
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    writeln!(handle, "{}", line).unwrap();
    handle.flush().unwrap();
}

fn main() {
    // Redirect panics to stderr rather than just aborting silently.
    std::panic::set_hook(Box::new(|info| {
        let msg = if let Some(s) = info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "unknown panic".to_string()
        };
        let loc = info.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
        eprintln!("PANIC at {loc}: {msg}");
    }));

    let stdin = io::stdin();
    let reader = BufReader::new(stdin.lock());

    let mut engine: Option<AheResNetEngine<rand::rngs::StdRng>> = None;

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }

        let req: Request = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                emit_error(&format!("parse error: {e}"));
                continue;
            }
        };

        match req {
            Request::Init {
                weights_dir,
                pubkey_x,
                pubkey_y,
            } => {
                eprintln!("[worker] init weights_dir={weights_dir}",);
                let weights = match load_resnet_weights(&PathBuf::from(&weights_dir)) {
                    Ok(w) => w,
                    Err(e) => {
                        emit_error(&format!("weight load error: {e}"));
                        continue;
                    }
                };
                let pk = {
                    let x = BigUint::parse_bytes(pubkey_x.as_bytes(), 10)
                        .or_else(|| BigUint::parse_bytes(pubkey_x.as_bytes(), 16));
                    let y = BigUint::parse_bytes(pubkey_y.as_bytes(), 10)
                        .or_else(|| BigUint::parse_bytes(pubkey_y.as_bytes(), 16));
                    let (x, y) = match (x, y) {
                        (Some(x), Some(y)) => (x, y),
                        _ => {
                            emit_error("invalid pubkey_x/y");
                            continue;
                        }
                    };
                    let mut xb = x.to_bytes_be();
                    let mut yb = y.to_bytes_be();
                    if xb.len() < 32 {
                        let mut pad = vec![0u8; 32 - xb.len()];
                        pad.extend_from_slice(&xb);
                        xb = pad;
                    }
                    if yb.len() < 32 {
                        let mut pad = vec![0u8; 32 - yb.len()];
                        pad.extend_from_slice(&yb);
                        yb = pad;
                    }
                    let mut x_arr = [0u8; 32];
                    let mut y_arr = [0u8; 32];
                    x_arr.copy_from_slice(&xb[xb.len() - 32..]);
                    y_arr.copy_from_slice(&yb[yb.len() - 32..]);
                    E2Point::Affine {
                        x: x_arr,
                        y: y_arr,
                    }
                };
                let rng = StdRng::from_entropy();
                engine = Some(AheResNetEngine::new(pk, weights, rng));
                emit_ok(&OkResponse {
                    ok: true,
                    out_c1_xy: None,
                    out_c2_xy: None,
                    shape: None,
                    truncate: None,
                    inference_complete: false,
                    add: 0,
                    mult: 0,
                });
            }
            Request::Step {
                phase_id,
                c1_xy,
                c2_xy,
                shape,
            } => {
                let eng = match engine.as_mut() {
                    Some(e) => e,
                    None => {
                        emit_error("engine not initialized");
                        continue;
                    }
                };

                let c1: Vec<E2Point> = c1_xy.iter().map(parse_point).collect();
                let c2: Vec<E2Point> = c2_xy.iter().map(parse_point).collect();
                let c1_ct4 = reshape_flat(c1, &shape);
                let c2_ct4 = reshape_flat(c2, &shape);

                let result = if phase_id == "initial" {
                    match eng.bind_initial_ciphertext(c1_ct4, c2_ct4) {
                        Ok(r) => r,
                        Err(e) => {
                            emit_error(&format!("engine error: {e}"));
                            continue;
                        }
                    }
                } else {
                    match eng.accept_client_ciphertext(&phase_id, c1_ct4, c2_ct4) {
                        Ok(r) => r,
                        Err(e) => {
                            emit_error(&format!("engine error: {e}"));
                            continue;
                        }
                    }
                };

                let out_c1_flat = result
                    .output_c1
                    .as_ref()
                    .map(|c| flatten_ct4(c).iter().map(point_to_xy).collect());
                let out_c2_flat = result
                    .output_c2
                    .as_ref()
                    .map(|c| flatten_ct4(c).iter().map(point_to_xy).collect());
                // Use truncate shape for output when inference is complete
                // (logits are 2-D [1,10] even though internally stored as [1,10,1,1] Ct4)
                let out_shape = if result.inference_complete {
                    result.truncate.as_ref().map(|t| t.shape.clone())
                } else {
                    result
                        .output_c1
                        .as_ref()
                        .map(|c| vec![c.len(), c[0].len(), c[0][0].len(), c[0][0][0].len()])
                };

                let trunc = result.truncate.as_ref().map(|t| TruncateInfo {
                    phase_id: t.phase_id.clone(),
                    client_action: t.client_action.clone(),
                    shift_bits: t.shift_bits,
                    shape: t.shape.clone(),
                    pool_kernel: t.pool_kernel,
                    input_shape: t.input_shape.clone(),
                });

                emit_ok(&OkResponse {
                    ok: true,
                    out_c1_xy: out_c1_flat,
                    out_c2_xy: out_c2_flat,
                    shape: out_shape,
                    truncate: trunc,
                    inference_complete: result.inference_complete,
                    add: result.num_pt_add,
                    mult: result.num_pt_mult,
                });
            }
        }
    }
}
