use axum::{extract::State, Json};
use num_bigint::BigUint;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

use ovds_core::protocol;
use ovds_core::types::VerificationKey;
use ovds_core::BlsSecretKey;

use crate::SharedState;

// ---------------------------------------------------------------------------
// Request/Response types
// ---------------------------------------------------------------------------

#[derive(Deserialize)] pub struct AppendRequest { pub value: String }
#[derive(Serialize)] pub struct AppendResponse { pub index: u64, pub value: String, pub sigma_hex: String, pub tag_hex: String }
#[derive(Deserialize)] pub struct AppendBatchRequest { pub values: Vec<String> }
#[derive(Deserialize)] pub struct QueryRequest { pub index: u64 }
#[derive(Deserialize)] pub struct QueryBatchRequest { pub indices: Vec<u64> }
#[derive(Deserialize)] pub struct VerifyRequest { pub vk: VerificationKey, pub resp: ovds_core::QueryResponse }
#[derive(Serialize)] pub struct ErrorResponse { pub error: String }

// ---------------------------------------------------------------------------
// Full persistence: save + restore entire state
// ---------------------------------------------------------------------------

fn persist_full(state: &SharedState) -> Result<(), String> {
    let ss = state.server_state.try_read().map_err(|e| e.to_string())?;
    let ss = ss.as_ref().ok_or("no server state")?;
    let sk = state.sk.try_read().map_err(|e| e.to_string())?;
    let sk = sk.as_ref().ok_or("no sk")?;
    let vk = state.vk.try_read().map_err(|e| e.to_string())?;
    let vk = vk.as_ref().ok_or("no vk")?;

    let data = serde_json::json!({
        "vk": vk,
        "alpha": hex::encode(&sk.alpha.0),
        "cnt": sk.cnt,
        "acc_r": ss.acc_r.to_str_radix(10),
        "z_star": ss.z_star.to_str_radix(10),
        "n": ss.n.to_str_radix(10),
        "phi": ss.phi.to_str_radix(10),
        "r": ss.r.iter().map(|t| hex::encode(t.to_bytes_be())).collect::<Vec<_>>(),
        "db": ss.db.iter().map(|(i, rec)| {
            serde_json::json!({
                "i": i,
                "s": rec.s.to_str_radix(10),
                "sigma": hex::encode(&rec.sigma.0),
                "tag": hex::encode(&rec.tag.to_bytes_be()),
            })
        }).collect::<Vec<_>>(),
    });

    state.db.insert("state", data.to_string().as_bytes()).map_err(|e| e.to_string())?;
    state.db.flush().map_err(|e| e.to_string())?;
    Ok(())
}

pub async fn try_restore(state: &SharedState) -> Result<(), String> {
    let raw = state.db.get("state").map_err(|e| e.to_string())?.ok_or("no persisted state")?;
    let data: serde_json::Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;

    let vk: VerificationKey = serde_json::from_value(data["vk"].clone()).map_err(|e| e.to_string())?;
    let alpha_bytes = hex::decode(data["alpha"].as_str().unwrap_or("")).map_err(|e| e.to_string())?;
    let alpha = BlsSecretKey(alpha_bytes.try_into().map_err(|_| "bad alpha len")?);
    let cnt: u64 = data["cnt"].as_u64().unwrap_or(0);

    let n = BigUint::parse_bytes(data["n"].as_str().unwrap_or("0").as_bytes(), 10).unwrap_or_default();
    let phi = BigUint::parse_bytes(data["phi"].as_str().unwrap_or("0").as_bytes(), 10).unwrap_or_default();
    let acc_r = BigUint::parse_bytes(data["acc_r"].as_str().unwrap_or("0").as_bytes(), 10).unwrap_or_default();
    let z_star = BigUint::parse_bytes(data["z_star"].as_str().unwrap_or("0").as_bytes(), 10).unwrap_or_default();

    let r: HashSet<BigUint> = data["r"].as_array().unwrap_or(&vec![]).iter()
        .filter_map(|v| v.as_str())
        .map(|s| BigUint::from_bytes_be(&hex::decode(s).unwrap_or_default()))
        .collect();

    let mut db = HashMap::new();
    for entry in data["db"].as_array().unwrap_or(&vec![]) {
        let i = entry["i"].as_u64().unwrap_or(0);
        let s = BigUint::parse_bytes(entry["s"].as_str().unwrap_or("0").as_bytes(), 10).unwrap_or_default();
        let sigma_bytes = hex::decode(entry["sigma"].as_str().unwrap_or("")).unwrap_or_default();
        let tag = BigUint::from_bytes_be(&hex::decode(entry["tag"].as_str().unwrap_or("")).unwrap_or_default());
        db.insert(i, ovds_core::Record {
            s,
            sigma: ovds_core::BlsSignature(sigma_bytes),
            tag,
        });
    }

    *state.vk.write().await = Some(vk.clone());
    let sk = ovds_core::SecretKey { alpha, cnt, vk };
    *state.sk.write().await = Some(sk);
    *state.server_state.write().await = Some(ovds_core::ServerState {
        vk: state.vk.read().await.clone().unwrap(),
        r, db, acc_r, z_star, n, phi,
    });
    tracing::info!("Restored full state: {} records, cnt={}", state.server_state.read().await.as_ref().unwrap().db.len(), cnt);
    Ok(())
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

pub async fn setup(State(state): State<SharedState>) -> Result<Json<VerificationKey>, Json<ErrorResponse>> {
    match protocol::setup() {
        Ok((vk, sk, ss)) => {
            *state.vk.write().await = Some(vk.clone());
            *state.sk.write().await = Some(sk);
            *state.server_state.write().await = Some(ss);
            let _ = persist_full(&state);
            Ok(Json(vk))
        }
        Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
    }
}

pub async fn append(State(state): State<SharedState>, Json(req): Json<AppendRequest>) -> Result<Json<AppendResponse>, Json<ErrorResponse>> {
    let val = BigUint::parse_bytes(req.value.as_bytes(), 10).unwrap_or_default();
    let result;
    {
        let mut _sk = state.sk.write().await;
        let mut _ss = state.server_state.write().await;
        result = match (&mut *_sk, &mut *_ss) {
            (Some(sk), Some(ss)) => match protocol::append(sk, &val, ss) {
                Ok((i, rec)) => Ok(Json(json_append(i, &rec))),
                Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
            },
            _ => Err(Json(ErrorResponse { error: "not setup".into() })),
        };
    } // locks dropped here
    let _ = persist_full(&state);
    result
}

/// Batch append: sign all values first (fast, sequential), then verify+store.
pub async fn append_batch(State(state): State<SharedState>, Json(req): Json<AppendBatchRequest>) -> Result<Json<Vec<AppendResponse>>, Json<ErrorResponse>> {
    // Phase 1+2: sign and verify
    let result;
    {
        let mut _sk = state.sk.write().await;
        let mut _ss = state.server_state.write().await;
        let (sk, ss) = match (&mut *_sk, &mut *_ss) {
            (Some(s), Some(ss)) => (s, ss),
            _ => return Err(Json(ErrorResponse { error: "not setup".into() })),
        };
        let mut pending = Vec::new();
        for v in &req.values {
            let val = BigUint::parse_bytes(v.as_bytes(), 10).unwrap_or_default();
            let (i, record) = protocol::append_client(sk, &val);
            pending.push((i, record));
        }
        for (i, record) in &pending {
            protocol::append_server(&sk.vk, ss, *i, record)
                .map_err(|e| Json(ErrorResponse { error: e.to_string() }))?;
        }
        result = Ok(Json(pending.iter().map(|(i, r)| json_append(*i, r)).collect()));
    } // locks dropped
    let _ = persist_full(&state);
    result
}

pub async fn query_single(State(state): State<SharedState>, Json(req): Json<QueryRequest>) -> Result<Json<serde_json::Value>, Json<ErrorResponse>> {
    let ss = state.server_state.read().await;
    match &*ss {
        Some(ss) => match protocol::query(ss, req.index) {
            Ok(resp) => Ok(Json(serde_json::json!({
                "index": resp.index, "value": resp.value.to_str_radix(10),
                "proof": { "sigma_hex": hex::encode(&resp.proof.sigma.0), "tag_hex": hex::encode(&resp.proof.tag.to_bytes_be()) }
            }))),
            Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
        },
        None => Err(Json(ErrorResponse { error: "not setup".into() })),
    }
}

pub async fn query_batch(State(state): State<SharedState>, Json(req): Json<QueryBatchRequest>) -> Result<Json<serde_json::Value>, Json<ErrorResponse>> {
    let ss = state.server_state.read().await;
    match &*ss {
        Some(ss) => match protocol::query_star(ss, &req.indices) {
            Ok(resp) => Ok(Json(serde_json::json!({
                "values": resp.values.iter().map(|(i,v)| serde_json::json!([i, [v.to_str_radix(10)]])).collect::<Vec<_>>(),
                "proof": { "items": resp.proof.items.iter().map(|(i,s,t)| serde_json::json!([i, hex::encode(&s.0), hex::encode(&t.to_bytes_be())])).collect::<Vec<_>>() }
            }))),
            Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
        },
        None => Err(Json(ErrorResponse { error: "not setup".into() })),
    }
}

pub async fn verify(Json(req): Json<VerifyRequest>) -> Result<Json<serde_json::Value>, Json<ErrorResponse>> {
    match protocol::verify_query(&req.vk, &req.resp) {
        Ok(valid) => Ok(Json(serde_json::json!({"valid": valid}))),
        Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
    }
}

pub async fn verify_batch(Json(req): Json<serde_json::Value>) -> Result<Json<serde_json::Value>, Json<ErrorResponse>> {
    let vk: VerificationKey = serde_json::from_value(req.get("vk").cloned().unwrap_or_default()).map_err(|e| ErrorResponse{error:e.to_string()})?;
    let resp: ovds_core::QueryStarResponse = serde_json::from_value(req.get("resp").cloned().unwrap_or_default()).map_err(|e| ErrorResponse{error:e.to_string()})?;
    match protocol::verify_query_star(&vk, &resp) {
        Ok(valid) => Ok(Json(serde_json::json!({"valid": valid}))),
        Err(e) => Err(Json(ErrorResponse { error: e.to_string() })),
    }
}

fn json_append(i: u64, rec: &ovds_core::Record) -> AppendResponse {
    AppendResponse { index: i, value: rec.s.to_str_radix(10), sigma_hex: hex::encode(&rec.sigma.0), tag_hex: hex::encode(&rec.tag.to_bytes_be()) }
}
