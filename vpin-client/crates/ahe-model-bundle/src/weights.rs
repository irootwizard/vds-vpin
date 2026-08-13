use std::path::Path;

use ndarray::Array2;
use ndarray_npy::ReadNpyExt;
use thiserror::Error;

#[derive(Clone, Debug)]
pub struct NetworkAWeights {
    pub weight_fc1: Array2<f64>,
    pub bias_fc1: ndarray::Array1<f64>,
    pub weight_fc2: Array2<f64>,
    pub bias_fc2: ndarray::Array1<f64>,
}

#[derive(Error, Debug)]
pub enum WeightsError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("npy: {0}")]
    Npy(#[from] ndarray_npy::ReadNpyError),
}

pub fn load_network_a_weights(dir: &Path) -> Result<NetworkAWeights, WeightsError> {
    let load2 = |name: &str| -> Result<Array2<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(Array2::read_npy(&mut r)?)
    };
    let load1 = |name: &str| -> Result<ndarray::Array1<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array1::read_npy(&mut r)?)
    };
    Ok(NetworkAWeights {
        weight_fc1: load2("weight_fc1_64_16.npy")?,
        bias_fc1: load1("bias_fc1_16.npy")?,
        weight_fc2: load2("weight_fc2_16_10.npy")?,
        bias_fc2: load1("bias_fc2_10.npy")?,
    })
}

pub const CONV_FILTER: [[i64; 3]; 3] = [[1, 0, 1], [2, 0, 2], [1, 0, 1]];
