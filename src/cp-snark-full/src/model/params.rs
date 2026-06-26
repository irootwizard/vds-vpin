//! Typed model **W** for `layer_proof` / `commit` (not EC trace scalars).

/// Convolution hyperparameters (public, non-learned).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConvHyper {
    pub stride: usize,
    pub padding: usize,
}

/// One conv layer: filter coefficients only (vPIN network A: single 3×3).
#[derive(Clone, Debug)]
pub struct ConvParams {
    pub filter_flat: Vec<u128>,
    pub hyper: ConvHyper,
}

/// Average-pool public hyperparameters.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PoolHyper {
    pub kernel: usize,
    pub stride: usize,
    /// Fixed-point representation of `1/kernel²` (Server.py `bits=10` path).
    pub inv_k_squared_fp: u128,
}

/// One FC layer: `weights[k][j] = W[k,j]`, `bias[j]`.
#[derive(Clone, Debug)]
pub struct FcParams {
    pub weights: Vec<Vec<u128>>,
    pub bias: Vec<u128>,
}

/// Full static CNN parameters for a network instance.
#[derive(Clone, Debug)]
pub struct ModelParams {
    pub network_id: String,
    pub conv: ConvParams,
    pub pool: PoolHyper,
    pub fc: Vec<FcParams>,
}

impl ModelParams {
    pub fn fc1(&self) -> Option<&FcParams> {
        self.fc.first()
    }

    pub fn fc2(&self) -> Option<&FcParams> {
        self.fc.get(1)
    }
}
