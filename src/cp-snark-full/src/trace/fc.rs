//! FC layer traces from `model_exports/{net}/fc_trace.json`.

use std::fs;
use std::path::PathBuf;

use serde::Deserialize;

use super::build::FcTraceInput;

#[derive(Debug, Deserialize)]
pub struct FcTraceFile {
    pub layers: Vec<FcLayerTraceJson>,
}

#[derive(Debug, Deserialize)]
pub struct FcLayerTraceJson {
    pub input_row: Vec<String>,
    pub output_row: Vec<String>,
}

fn path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("fc_trace.json")
}

fn parse_u128_vec(v: &[String]) -> Result<Vec<u128>, String> {
    v.iter()
        .map(|s| s.parse().map_err(|e| format!("{s}: {e}")))
        .collect()
}

pub fn load_fc_traces(network: &str) -> Result<Vec<FcTraceInput>, String> {
    let p = path(network);
    if !p.is_file() {
        return Ok(vec![]);
    }
    let json = fs::read_to_string(&p).map_err(|e| e.to_string())?;
    let f: FcTraceFile = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    f.layers
        .iter()
        .map(|layer| {
            Ok(FcTraceInput {
                inputs: parse_u128_vec(&layer.input_row)?,
                outputs: parse_u128_vec(&layer.output_row)?,
            })
        })
        .collect()
}
