//! Pool layer trace from `model_exports/{net}/pool_trace.json`.

use std::fs;
use std::path::PathBuf;

use serde::Deserialize;

use super::build::PoolTraceInput;

#[derive(Debug, Deserialize)]
pub struct PoolTraceBundle {
    pub kernel: usize,
    pub stride: usize,
    pub inv_k_squared_fp: String,
    pub windows: Vec<Vec<String>>,
    pub output_flat: Vec<String>,
}

use crate::trace::paths::trace_file;

fn path(network: &str) -> PathBuf {
    trace_file(network, "pool_trace.json")
}

fn parse_u128_vec(v: &[String]) -> Result<Vec<u128>, String> {
    v.iter()
        .map(|s| s.parse().map_err(|e| format!("{s}: {e}")))
        .collect()
}

pub fn load_pool_trace(network: &str) -> Result<Option<PoolTraceInput>, String> {
    let p = path(network);
    if !p.is_file() {
        return Ok(None);
    }
    let json = fs::read_to_string(&p).map_err(|e| e.to_string())?;
    let b: PoolTraceBundle = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    let windows: Vec<Vec<u128>> = b
        .windows
        .iter()
        .map(|w| parse_u128_vec(w))
        .collect::<Result<_, _>>()?;
    let output_sums = parse_u128_vec(&b.output_flat)?;
    let inv_k_squared_fp = b
        .inv_k_squared_fp
        .parse::<u128>()
        .map_err(|e| format!("pool inv_k_squared_fp: {e}"))?;
    Ok(Some(PoolTraceInput {
        windows,
        output_sums,
        inv_k_squared_fp,
    }))
}
