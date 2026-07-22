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

// ---------------------------------------------------------------------------
// LeNet weight structs
// ---------------------------------------------------------------------------

/// LeNet-MNIST weights (1-channel input).
/// Conv weights stored as (C_out, C_in, 5, 5).
/// FC weights stored as (in_features, out_features) — see export_weights.py.
#[derive(Clone, Debug)]
pub struct LeNetMnistWeights {
    /// (6, 1, 5, 5) — conv1 filter
    pub conv1_weight: ndarray::Array4<f64>,
    pub conv1_bias: ndarray::Array1<f64>,
    /// (16, 6, 5, 5) — conv2 filter
    pub conv2_weight: ndarray::Array4<f64>,
    pub conv2_bias: ndarray::Array1<f64>,
    /// (400, 120) — c3 treated as FC
    pub c3_weight: ndarray::Array2<f64>,
    pub c3_bias: ndarray::Array1<f64>,
    /// (120, 84)
    pub fc4_weight: ndarray::Array2<f64>,
    pub fc4_bias: ndarray::Array1<f64>,
    /// (84, 10)
    pub fc5_weight: ndarray::Array2<f64>,
    pub fc5_bias: ndarray::Array1<f64>,
}

/// LeNet-CIFAR10 weights (3-channel input).
#[derive(Clone, Debug)]
pub struct LeNetCifarWeights {
    /// (6, 3, 5, 5)
    pub conv1_weight: ndarray::Array4<f64>,
    pub conv1_bias: ndarray::Array1<f64>,
    pub conv2_weight: ndarray::Array4<f64>,
    pub conv2_bias: ndarray::Array1<f64>,
    pub c3_weight: ndarray::Array2<f64>,
    pub c3_bias: ndarray::Array1<f64>,
    pub fc4_weight: ndarray::Array2<f64>,
    pub fc4_bias: ndarray::Array1<f64>,
    pub fc5_weight: ndarray::Array2<f64>,
    pub fc5_bias: ndarray::Array1<f64>,
}

fn load4(dir: &std::path::Path, name: &str) -> Result<ndarray::Array4<f64>, WeightsError> {
    use ndarray_npy::ReadNpyExt;
    let mut r = std::fs::File::open(dir.join(name))?;
    Ok(ndarray::Array4::read_npy(&mut r)?)
}

pub fn load_lenet_mnist_weights(dir: &std::path::Path) -> Result<LeNetMnistWeights, WeightsError> {
    use ndarray_npy::ReadNpyExt;
    let load2 = |name: &str| -> Result<ndarray::Array2<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array2::read_npy(&mut r)?)
    };
    let load1 = |name: &str| -> Result<ndarray::Array1<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array1::read_npy(&mut r)?)
    };
    Ok(LeNetMnistWeights {
        conv1_weight: load4(dir, "conv1_weight_6_1_5_5.npy")?,
        conv1_bias:   load1("conv1_bias_6.npy")?,
        conv2_weight: load4(dir, "conv2_weight_16_6_5_5.npy")?,
        conv2_bias:   load1("conv2_bias_16.npy")?,
        c3_weight:    load2("c3_weight_400_120.npy")?,
        c3_bias:      load1("c3_bias_120.npy")?,
        fc4_weight:   load2("fc4_weight_120_84.npy")?,
        fc4_bias:     load1("fc4_bias_84.npy")?,
        fc5_weight:   load2("fc5_weight_84_10.npy")?,
        fc5_bias:     load1("fc5_bias_10.npy")?,
    })
}

pub fn load_lenet_cifar_weights(dir: &std::path::Path) -> Result<LeNetCifarWeights, WeightsError> {
    use ndarray_npy::ReadNpyExt;
    let load2 = |name: &str| -> Result<ndarray::Array2<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array2::read_npy(&mut r)?)
    };
    let load1 = |name: &str| -> Result<ndarray::Array1<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array1::read_npy(&mut r)?)
    };
    Ok(LeNetCifarWeights {
        conv1_weight: load4(dir, "conv1_weight_6_3_5_5.npy")?,
        conv1_bias:   load1("conv1_bias_6.npy")?,
        conv2_weight: load4(dir, "conv2_weight_16_6_5_5.npy")?,
        conv2_bias:   load1("conv2_bias_16.npy")?,
        c3_weight:    load2("c3_weight_400_120.npy")?,
        c3_bias:      load1("c3_bias_120.npy")?,
        fc4_weight:   load2("fc4_weight_120_84.npy")?,
        fc4_bias:     load1("fc4_bias_84.npy")?,
        fc5_weight:   load2("fc5_weight_84_10.npy")?,
        fc5_bias:     load1("fc5_bias_10.npy")?,
    })
}

// ---------------------------------------------------------------------------
// ResNet18 weights
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct ResNetWeights {
    pub stem_w: ndarray::Array4<f64>,
    pub stem_b: ndarray::Array1<f64>,
    pub l1b0_conv1_w: ndarray::Array4<f64>,
    pub l1b0_conv1_b: ndarray::Array1<f64>,
    pub l1b0_conv2_w: ndarray::Array4<f64>,
    pub l1b0_conv2_b: ndarray::Array1<f64>,
    pub l1b1_conv1_w: ndarray::Array4<f64>,
    pub l1b1_conv1_b: ndarray::Array1<f64>,
    pub l1b1_conv2_w: ndarray::Array4<f64>,
    pub l1b1_conv2_b: ndarray::Array1<f64>,
    pub l2b0_conv1_w: ndarray::Array4<f64>,
    pub l2b0_conv1_b: ndarray::Array1<f64>,
    pub l2b0_conv2_w: ndarray::Array4<f64>,
    pub l2b0_conv2_b: ndarray::Array1<f64>,
    pub l2b0_ds_w: ndarray::Array4<f64>,
    pub l2b0_ds_b: ndarray::Array1<f64>,
    pub l2b1_conv1_w: ndarray::Array4<f64>,
    pub l2b1_conv1_b: ndarray::Array1<f64>,
    pub l2b1_conv2_w: ndarray::Array4<f64>,
    pub l2b1_conv2_b: ndarray::Array1<f64>,
    pub l3b0_conv1_w: ndarray::Array4<f64>,
    pub l3b0_conv1_b: ndarray::Array1<f64>,
    pub l3b0_conv2_w: ndarray::Array4<f64>,
    pub l3b0_conv2_b: ndarray::Array1<f64>,
    pub l3b0_ds_w: ndarray::Array4<f64>,
    pub l3b0_ds_b: ndarray::Array1<f64>,
    pub l3b1_conv1_w: ndarray::Array4<f64>,
    pub l3b1_conv1_b: ndarray::Array1<f64>,
    pub l3b1_conv2_w: ndarray::Array4<f64>,
    pub l3b1_conv2_b: ndarray::Array1<f64>,
    pub l4b0_conv1_w: ndarray::Array4<f64>,
    pub l4b0_conv1_b: ndarray::Array1<f64>,
    pub l4b0_conv2_w: ndarray::Array4<f64>,
    pub l4b0_conv2_b: ndarray::Array1<f64>,
    pub l4b0_ds_w: ndarray::Array4<f64>,
    pub l4b0_ds_b: ndarray::Array1<f64>,
    pub l4b1_conv1_w: ndarray::Array4<f64>,
    pub l4b1_conv1_b: ndarray::Array1<f64>,
    pub l4b1_conv2_w: ndarray::Array4<f64>,
    pub l4b1_conv2_b: ndarray::Array1<f64>,
    pub linear_w: ndarray::Array2<f64>,
    pub linear_b: ndarray::Array1<f64>,
}

pub fn load_resnet_weights(dir: &Path) -> Result<ResNetWeights, WeightsError> {
    use ndarray_npy::ReadNpyExt;
    let load4 = |name: &str| -> Result<ndarray::Array4<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array4::read_npy(&mut r)?)
    };
    let load2 = |name: &str| -> Result<ndarray::Array2<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array2::read_npy(&mut r)?)
    };
    let load1 = |name: &str| -> Result<ndarray::Array1<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array1::read_npy(&mut r)?)
    };
    Ok(ResNetWeights {
        stem_w: load4("stem_weight_64_3_3_3.npy")?,
        stem_b: load1("stem_bias_64.npy")?,
        l1b0_conv1_w: load4("l1b0_conv1_weight_64_64_3_3.npy")?,
        l1b0_conv1_b: load1("l1b0_conv1_bias_64.npy")?,
        l1b0_conv2_w: load4("l1b0_conv2_weight_64_64_3_3.npy")?,
        l1b0_conv2_b: load1("l1b0_conv2_bias_64.npy")?,
        l1b1_conv1_w: load4("l1b1_conv1_weight_64_64_3_3.npy")?,
        l1b1_conv1_b: load1("l1b1_conv1_bias_64.npy")?,
        l1b1_conv2_w: load4("l1b1_conv2_weight_64_64_3_3.npy")?,
        l1b1_conv2_b: load1("l1b1_conv2_bias_64.npy")?,
        l2b0_conv1_w: load4("l2b0_conv1_weight_128_64_3_3.npy")?,
        l2b0_conv1_b: load1("l2b0_conv1_bias_128.npy")?,
        l2b0_conv2_w: load4("l2b0_conv2_weight_128_128_3_3.npy")?,
        l2b0_conv2_b: load1("l2b0_conv2_bias_128.npy")?,
        l2b0_ds_w: load4("l2b0_ds_weight_128_64_1_1.npy")?,
        l2b0_ds_b: load1("l2b0_ds_bias_128.npy")?,
        l2b1_conv1_w: load4("l2b1_conv1_weight_128_128_3_3.npy")?,
        l2b1_conv1_b: load1("l2b1_conv1_bias_128.npy")?,
        l2b1_conv2_w: load4("l2b1_conv2_weight_128_128_3_3.npy")?,
        l2b1_conv2_b: load1("l2b1_conv2_bias_128.npy")?,
        l3b0_conv1_w: load4("l3b0_conv1_weight_256_128_3_3.npy")?,
        l3b0_conv1_b: load1("l3b0_conv1_bias_256.npy")?,
        l3b0_conv2_w: load4("l3b0_conv2_weight_256_256_3_3.npy")?,
        l3b0_conv2_b: load1("l3b0_conv2_bias_256.npy")?,
        l3b0_ds_w: load4("l3b0_ds_weight_256_128_1_1.npy")?,
        l3b0_ds_b: load1("l3b0_ds_bias_256.npy")?,
        l3b1_conv1_w: load4("l3b1_conv1_weight_256_256_3_3.npy")?,
        l3b1_conv1_b: load1("l3b1_conv1_bias_256.npy")?,
        l3b1_conv2_w: load4("l3b1_conv2_weight_256_256_3_3.npy")?,
        l3b1_conv2_b: load1("l3b1_conv2_bias_256.npy")?,
        l4b0_conv1_w: load4("l4b0_conv1_weight_512_256_3_3.npy")?,
        l4b0_conv1_b: load1("l4b0_conv1_bias_512.npy")?,
        l4b0_conv2_w: load4("l4b0_conv2_weight_512_512_3_3.npy")?,
        l4b0_conv2_b: load1("l4b0_conv2_bias_512.npy")?,
        l4b0_ds_w: load4("l4b0_ds_weight_512_256_1_1.npy")?,
        l4b0_ds_b: load1("l4b0_ds_bias_512.npy")?,
        l4b1_conv1_w: load4("l4b1_conv1_weight_512_512_3_3.npy")?,
        l4b1_conv1_b: load1("l4b1_conv1_bias_512.npy")?,
        l4b1_conv2_w: load4("l4b1_conv2_weight_512_512_3_3.npy")?,
        l4b1_conv2_b: load1("l4b1_conv2_bias_512.npy")?,
        linear_w: load2("linear_weight_512_10.npy")?,
        linear_b: load1("linear_bias_10.npy")?,
    })
}

// ---------------------------------------------------------------------------
// SimpleCNN Face weights
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct SimpleCNNFaceWeights {
    pub conv1_w: ndarray::Array4<f64>,
    pub conv1_b: ndarray::Array1<f64>,
    pub conv2_w: ndarray::Array4<f64>,
    pub conv2_b: ndarray::Array1<f64>,
    pub conv3_w: ndarray::Array4<f64>,
    pub conv3_b: ndarray::Array1<f64>,
    pub fc1_w: ndarray::Array2<f64>,
    pub fc1_b: ndarray::Array1<f64>,
    pub fc2_w: ndarray::Array2<f64>,
    pub fc2_b: ndarray::Array1<f64>,
}

pub fn load_simple_cnn_face_weights(dir: &Path) -> Result<SimpleCNNFaceWeights, WeightsError> {
    use ndarray_npy::ReadNpyExt;
    let load4 = |name: &str| -> Result<ndarray::Array4<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array4::read_npy(&mut r)?)
    };
    let load2 = |name: &str| -> Result<ndarray::Array2<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array2::read_npy(&mut r)?)
    };
    let load1 = |name: &str| -> Result<ndarray::Array1<f64>, WeightsError> {
        let mut r = std::fs::File::open(dir.join(name))?;
        Ok(ndarray::Array1::read_npy(&mut r)?)
    };
    Ok(SimpleCNNFaceWeights {
        conv1_w: load4("conv1_weight_16_3_3_3.npy")?,
        conv1_b: load1("conv1_bias_16.npy")?,
        conv2_w: load4("conv2_weight_32_16_3_3.npy")?,
        conv2_b: load1("conv2_bias_32.npy")?,
        conv3_w: load4("conv3_weight_64_32_3_3.npy")?,
        conv3_b: load1("conv3_bias_64.npy")?,
        fc1_w: load2("fc1_weight_128_4096.npy")?,
        fc1_b: load1("fc1_bias_128.npy")?,
        fc2_w: load2("fc2_weight_K_128.npy")?,
        fc2_b: load1("fc2_bias_K.npy")?,
    })
}
