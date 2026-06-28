//! Load [`ModelParams`] from manifest / export files / built-in network tables.

use std::fs;
use std::path::PathBuf;

use serde::Deserialize;

use super::manifest::{ModelManifest, ModelSource};
use super::params::{ConvHyper, ConvParams, FcParams, ModelParams, PoolHyper};

#[derive(Clone, Debug)]
pub enum ModelLoadError {
    UnknownNetwork(String),
    UnsupportedSource(String),
    Io(String),
    Parse(String),
}

impl std::fmt::Display for ModelLoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

/// Same 3×3 kernel as `cnn_networks/Server.py` `callConv2_ciphertext` (inline, not .npy).
pub fn network_a_conv_filter_flat() -> Vec<u128> {
    vec![1, 0, 1, 2, 0, 2, 1, 0, 1]
}

/// Kernel / stride for vPIN version id (1–5) aligned with `KERNEL_STRIDE` in Server.py.
pub fn vpin_pool_hyper(version: u8) -> (usize, usize, u128) {
    let (kernel, stride) = match version {
        1 => (2, 2),
        2 => (2, 2),
        3 => (4, 4),
        4 => (4, 4),
        5 => (8, 8),
        _ => (2, 2),
    };
    // Server uses realNumbersToFixedPointRepresentation(1/(k²), type=2, bits=10)
    let inv = ((1u128 << 10) + (kernel * kernel) as u128 / 2) / (kernel * kernel) as u128;
    (kernel, stride, inv)
}

fn manifest_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("model_export.json")
}

fn full_weights_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("full_weights.json")
}

/// Expected $|W^*|$ for network A (docs: 9 + 1024 + 16 + 160 + 10).
pub const NETWORK_A_W_STAR_LEN: usize = 1219;

/// JSON export of full static $\mathbf{W}^*$ (conv + FC fixed-point scalars).
#[derive(Debug, Deserialize)]
pub struct FullWeightsJson {
    pub network_id: String,
    pub num_weights: usize,
    pub w_star_flat: Vec<String>,
}

/// Load complete $\mathbf{W}^*$ from an explicit path (model run export).
pub fn load_w_star_from_path(path: &std::path::Path) -> Result<Vec<u128>, ModelLoadError> {
    let json = fs::read_to_string(path)
        .map_err(|e| ModelLoadError::Io(format!("{path:?}: {e}")))?;
    parse_full_weights_json(&json)
}

pub fn load_w_star_from_run_dir(network: &str, run_dir: &std::path::Path) -> Result<Vec<u128>, ModelLoadError> {
    let path = run_dir.join("proof_artifacts").join("full_weights.json");
    let mut w = load_w_star_from_path(&path)?;
    if network == "A" && w.len() != NETWORK_A_W_STAR_LEN {
        return Err(ModelLoadError::Parse(format!(
            "network A: expected {} weights, got {}",
            NETWORK_A_W_STAR_LEN,
            w.len()
        )));
    }
    Ok(w)
}

fn parse_full_weights_json(json: &str) -> Result<Vec<u128>, ModelLoadError> {
    let exp: FullWeightsJson =
        serde_json::from_str(json).map_err(|e| ModelLoadError::Parse(e.to_string()))?;
    let weights: Vec<u128> = exp
        .w_star_flat
        .iter()
        .map(|s| {
            s.parse::<u128>()
                .map_err(|e| ModelLoadError::Parse(format!("{s}: {e}")))
        })
        .collect::<Result<_, _>>()?;
    if weights.len() != exp.num_weights {
        return Err(ModelLoadError::Parse(format!(
            "num_weights {} != flat len {}",
            exp.num_weights,
            weights.len()
        )));
    }
    Ok(weights)
}

/// Load complete $\mathbf{W}^*$ vector for commitment / L1 binding.
///
/// Reads `model_exports/{network}/full_weights.json` produced by
/// `python/export_full_weights.py`.
pub fn load_w_star(network: &str) -> Result<Vec<u128>, ModelLoadError> {
    if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        return load_w_star_from_run_dir(network, std::path::Path::new(&run));
    }
    let path = full_weights_path(network);
    let json = fs::read_to_string(&path)
        .map_err(|e| ModelLoadError::Io(format!("{path:?}: {e}")))?;
    let exp: FullWeightsJson =
        serde_json::from_str(&json).map_err(|e| ModelLoadError::Parse(e.to_string()))?;
    if exp.network_id != network {
        return Err(ModelLoadError::Parse(format!(
            "full_weights network_id {:?} != {:?}",
            exp.network_id, network
        )));
    }
    let weights = parse_full_weights_json(&json)?;
    if network == "A" && weights.len() != NETWORK_A_W_STAR_LEN {
        return Err(ModelLoadError::Parse(format!(
            "network A: expected {} weights, got {}",
            NETWORK_A_W_STAR_LEN,
            weights.len()
        )));
    }
    Ok(weights)
}

/// JSON export shape (optional file; can be produced from `.npy` or HF flatten script).
#[derive(Debug, Deserialize)]
struct ModelExportJson {
    network_id: String,
    conv_filter_flat: Vec<String>,
    pool: PoolExportJson,
    fc: Vec<FcExportJson>,
}

#[derive(Debug, Deserialize)]
struct PoolExportJson {
    kernel: usize,
    stride: usize,
    inv_k_squared_fp: String,
}

#[derive(Debug, Deserialize)]
struct FcExportJson {
    weights: Vec<Vec<String>>,
    bias: Vec<String>,
}

fn parse_u128_list(rows: &[Vec<String>]) -> Result<Vec<Vec<u128>>, ModelLoadError> {
    rows.iter()
        .map(|row| {
            row.iter()
                .map(|s| {
                    s.parse::<u128>()
                        .map_err(|e| ModelLoadError::Parse(format!("{s}: {e}")))
                })
                .collect()
        })
        .collect()
}

/// Load [`ModelParams`] from a `model_export.json` path (storage / ingest).
pub fn load_from_export_path(path: &PathBuf) -> Result<ModelParams, ModelLoadError> {
    let json = fs::read_to_string(path).map_err(|e| ModelLoadError::Io(e.to_string()))?;
    let exp: ModelExportJson =
        serde_json::from_str(&json).map_err(|e| ModelLoadError::Parse(e.to_string()))?;
    let conv_filter_flat: Vec<u128> = exp
        .conv_filter_flat
        .iter()
        .map(|s| {
            s.parse::<u128>()
                .map_err(|e| ModelLoadError::Parse(format!("{s}: {e}")))
        })
        .collect::<Result<_, _>>()?;
    let fc: Vec<FcParams> = exp
        .fc
        .into_iter()
        .map(|layer| {
            Ok(FcParams {
                weights: parse_u128_list(&layer.weights)?,
                bias: layer
                    .bias
                    .iter()
                    .map(|s| {
                        s.parse::<u128>()
                            .map_err(|e| ModelLoadError::Parse(format!("{s}: {e}")))
                    })
                    .collect::<Result<_, _>>()?,
            })
        })
        .collect::<Result<_, ModelLoadError>>()?;
    Ok(ModelParams {
        network_id: exp.network_id,
        conv: ConvParams {
            filter_flat: conv_filter_flat,
            hyper: ConvHyper {
                stride: 1,
                padding: 1,
            },
        },
        pool: PoolHyper {
            kernel: exp.pool.kernel,
            stride: exp.pool.stride,
            inv_k_squared_fp: exp.pool.inv_k_squared_fp.parse::<u128>().map_err(|e| {
                ModelLoadError::Parse(format!("pool.inv_k_squared_fp: {e}"))
            })?,
        },
        fc,
    })
}

/// Load static **W** for a logical network name (`"A"`, …).
///
/// Priority: `model_exports/{network}/model_export.json` → built-in vPIN tables (conv + pool;
/// FC layers empty until export exists).
pub fn load_model_params(network: &str) -> Result<ModelParams, ModelLoadError> {
    let export = manifest_path(network);
    if export.is_file() {
        return load_from_export_path(&export);
    }

    let version = network_to_vpin_version(network)?;
    let (pool_k, pool_s, inv_fp) = vpin_pool_hyper(version);
    Ok(ModelParams {
        network_id: network.to_string(),
        conv: ConvParams {
            filter_flat: network_a_conv_filter_flat(),
            hyper: ConvHyper {
                stride: 1,
                padding: 1,
            },
        },
        pool: PoolHyper {
            kernel: pool_k,
            stride: pool_s,
            inv_k_squared_fp: inv_fp,
        },
        fc: vec![],
    })
}

pub fn load_from_manifest(manifest: &ModelManifest) -> Result<ModelParams, ModelLoadError> {
    match &manifest.source {
        ModelSource::VpinNpy { version } => {
            let folder = manifest
                .vpin_layout
                .as_ref()
                .map(|l| l.network_folder.as_str())
                .unwrap_or("A");
            let mut p = load_model_params(folder)?;
            let (_k, _s, inv) = vpin_pool_hyper(*version);
            p.pool.inv_k_squared_fp = inv;
            Ok(p)
        }
        ModelSource::ExportedJson { path } => load_from_export_path(&PathBuf::from(path)),
        ModelSource::HuggingFace { .. } => Err(ModelLoadError::UnsupportedSource(
            "HuggingFace: add export script → model_export.json or impl safetensors loader"
                .into(),
        )),
    }
}

fn network_to_vpin_version(network: &str) -> Result<u8, ModelLoadError> {
    match network {
        "A" => Ok(1),
        "B" => Ok(2),
        "C" => Ok(3),
        "D" => Ok(4),
        "E" => Ok(5),
        other => Err(ModelLoadError::UnknownNetwork(other.to_string())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn network_a_conv_matches_server_inline() {
        assert_eq!(network_a_conv_filter_flat(), vec![1, 0, 1, 2, 0, 2, 1, 0, 1]);
    }

    #[test]
    fn load_model_params_a_has_conv_and_pool() {
        let m = load_model_params("A").unwrap();
        assert_eq!(m.conv.filter_flat.len(), 9);
        assert_eq!(m.pool.kernel, 2);
    }

    #[test]
    fn load_w_star_network_a_has_1219_weights() {
        let w = load_w_star("A").unwrap();
        assert_eq!(w.len(), NETWORK_A_W_STAR_LEN);
        // First 9 = inline conv kernel (Server.py)
        assert_eq!(&w[..9], &[1, 0, 1, 2, 0, 2, 1, 0, 1]);
    }
}
