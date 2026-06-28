//! FC layer traces from run `fc_trace.json`.

use std::fs;
use std::path::PathBuf;

use serde::Deserialize;

use super::build::FcTraceInput;
use crate::layer_proof::FcLayerProofSpec;
use crate::trace::paths::trace_file;

#[derive(Debug, Deserialize)]
pub struct FcTraceFile {
    pub layers: Vec<FcLayerTraceJson>,
}

#[derive(Debug, Deserialize)]
pub struct FcLayerTraceJson {
    #[serde(alias = "inputs")]
    pub input_row: Vec<String>,
    #[serde(alias = "outputs")]
    pub output_row: Vec<String>,
    #[serde(default)]
    pub bias: Vec<String>,
    #[serde(default)]
    pub weights_in_out: Vec<Vec<String>>,
}

fn path(network: &str) -> PathBuf {
    trace_file(network, "fc_trace.json")
}

fn parse_u128_vec(v: &[String]) -> Result<Vec<u128>, String> {
    v.iter()
        .map(|s| parse_fixed_point_u128(s))
        .collect()
}

/// Parse trace decimal (signed fixed-point mod $2^{32}$) to u128 field element.
fn parse_fixed_point_u128(s: &str) -> Result<u128, String> {
    if let Ok(v) = s.parse::<u128>() {
        return Ok(v);
    }
    let signed: i128 = s.parse().map_err(|e| format!("{s}: {e}"))?;
    const MOD: i128 = 1i128 << 32;
    let mut x = signed.rem_euclid(MOD);
    Ok(x as u128)
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
                weights_in_out: layer
                    .weights_in_out
                    .iter()
                    .map(|row| parse_u128_vec(row))
                    .collect::<Result<_, _>>()?,
                bias: if layer.bias.is_empty() {
                    vec![]
                } else {
                    parse_u128_vec(&layer.bias)?
                },
            })
        })
        .collect()
}

/// Load per-layer bias vectors from `fc_trace.json` (for chain-outside W* binding).
pub fn load_fc_trace_biases(network: &str) -> Result<Vec<Vec<u128>>, String> {
    let p = path(network);
    if !p.is_file() {
        return Ok(vec![]);
    }
    let json = fs::read_to_string(&p).map_err(|e| e.to_string())?;
    let f: FcTraceFile = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    f.layers
        .iter()
        .map(|layer| {
            if layer.bias.is_empty() {
                Ok(vec![])
            } else {
                parse_u128_vec(&layer.bias)
            }
        })
        .collect()
}

/// Full FC layer specs: activations from trace, static W* from run export.
pub fn load_fc_layer_specs(network: &str) -> Result<Vec<FcLayerProofSpec>, String> {
    let traces = load_fc_traces(network)?;
    if traces.is_empty() {
        return Ok(vec![]);
    }
    let w_star = crate::model::load_w_star(network).map_err(|e| e.to_string())?;
    if network == "A" && w_star.len() >= 1219 {
        return Ok(vec![
            FcLayerProofSpec {
                inputs: traces[0].inputs.clone(),
                outputs: traces[0].outputs.clone(),
                bias: w_star[1033..1049].to_vec(),
                weights_in_out: reshape_fc1_weights(&w_star[9..1033]),
            },
            FcLayerProofSpec {
                inputs: traces.get(1).map(|t| t.inputs.clone()).unwrap_or_default(),
                outputs: traces.get(1).map(|t| t.outputs.clone()).unwrap_or_default(),
                bias: w_star[1209..1219].to_vec(),
                weights_in_out: reshape_fc2_weights(&w_star[1049..1209]),
            },
        ]);
    }
    traces
        .into_iter()
        .map(|t| {
            Ok(FcLayerProofSpec {
                inputs: t.inputs,
                outputs: t.outputs,
                bias: t.bias,
                weights_in_out: t.weights_in_out,
            })
        })
        .collect()
}

fn reshape_fc1_weights(flat: &[u128]) -> Vec<Vec<u128>> {
    const INPUTS: usize = 64;
    const OUTPUTS: usize = 16;
    (0..INPUTS)
        .map(|k| {
            flat[k * OUTPUTS..(k + 1) * OUTPUTS]
                .to_vec()
        })
        .collect()
}

fn reshape_fc2_weights(flat: &[u128]) -> Vec<Vec<u128>> {
    const INPUTS: usize = 16;
    const OUTPUTS: usize = 10;
    (0..INPUTS)
        .map(|k| flat[k * OUTPUTS..(k + 1) * OUTPUTS].to_vec())
        .collect()
}
