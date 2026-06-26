//! Convolution **windows** / outputs — separate from PtMul `weight.json`.

use std::fs;
use std::path::PathBuf;

use serde::Deserialize;

use crate::layer_proof::ConvLayerProofSpec;

#[derive(Clone, Debug)]
pub enum ConvWitnessSource {
    /// Preferred M1: Python exports after `myConv2d` (see `model_exports/{net}/conv_trace.json`).
    TraceJson {
        bundle: ConvTraceBundle,
    },
    /// Recompute windows from padded plaintext/u128 grid (lab / tests only).
    RecomputePlaintext {
        padded: Vec<Vec<u128>>,
        stride: usize,
    },
    /// Not available — `build_linear_stack` skips conv or returns error.
    Missing,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ConvTraceBundle {
    pub filter_flat: Vec<String>,
    pub windows: Vec<Vec<String>>,
    pub output_flat: Vec<String>,
}

impl ConvTraceBundle {
    fn parse_u128_vec(v: &[String]) -> Result<Vec<u128>, String> {
        v.iter()
            .map(|s| s.parse().map_err(|e| format!("{s}: {e}")))
            .collect()
    }

    pub fn to_proof_spec(&self) -> Result<ConvLayerProofSpec, String> {
        let filter_flat = Self::parse_u128_vec(&self.filter_flat)?;
        let output_flat = Self::parse_u128_vec(&self.output_flat)?;
        let windows: Result<Vec<Vec<u128>>, String> = self
            .windows
            .iter()
            .map(|w| Self::parse_u128_vec(w))
            .collect();
        Ok(ConvLayerProofSpec {
            filter_flat,
            windows: windows?,
            output_flat,
        })
    }
}

pub fn conv_trace_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("conv_trace.json")
}

pub fn load_conv_trace(network: &str) -> Result<Option<ConvTraceBundle>, String> {
    let path = conv_trace_path(network);
    if !path.is_file() {
        return Ok(None);
    }
    let json = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let bundle: ConvTraceBundle = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    Ok(Some(bundle))
}

pub fn resolve_conv_source(
    network: &str,
    recompute: Option<(Vec<Vec<u128>>, usize)>,
) -> ConvWitnessSource {
    if let Ok(Some(bundle)) = load_conv_trace(network) {
        return ConvWitnessSource::TraceJson { bundle };
    }
    if let Some((padded, stride)) = recompute {
        return ConvWitnessSource::RecomputePlaintext { padded, stride };
    }
    ConvWitnessSource::Missing
}
