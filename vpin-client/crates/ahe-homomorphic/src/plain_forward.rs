//! Plain fixed-point Network A forward — semantic port of Python
//! `model_training.network_a.evaluate._numpy_homomorphic_plain`.

use ahe_codec::{apply_client_action, real_to_fixed_point, ClientAction};
use ahe_model_bundle::{NetworkAWeights, CONV_FILTER};
use ndarray::{Array1, Array2};

#[derive(Clone, Debug)]
pub struct TruncationPlan {
    pub shift_pool: u32,
    pub shift_fc1: u32,
    pub pool_inv_fp: i64,
}

impl Default for TruncationPlan {
    fn default() -> Self {
        Self {
            shift_pool: 26,
            shift_fc1: 32,
            pool_inv_fp: 64,
        }
    }
}

#[derive(Clone, Debug)]
pub struct PlainForwardLayers {
    pub after_fc2: Vec<i64>,
    pub prediction: usize,
}

pub fn conv2d_int32(input: &[i32], filter: &[[i64; 3]; 3]) -> Vec<i32> {
    let h = 32usize;
    let w = 32usize;
    debug_assert_eq!(input.len(), h * w);
    let pad = 1usize;
    let mut padded = vec![0i64; (h + 2 * pad) * (w + 2 * pad)];
    for i in 0..h {
        for j in 0..w {
            padded[(i + pad) * (w + 2 * pad) + (j + pad)] = input[i * w + j] as i64;
        }
    }
    let pw = w + 2 * pad;
    let mut out = vec![0i32; h * w];
    for i in 0..h {
        for j in 0..w {
            let mut sum = 0i64;
            for ii in 0..3 {
                for jj in 0..3 {
                    let v = padded[(i + ii) * pw + (j + jj)];
                    sum += v * filter[ii][jj];
                }
            }
            out[i * w + j] = sum as i32;
        }
    }
    out
}

pub fn pool_sum_fixed(after_conv: &[i64], pool_inv_fp: i64) -> Vec<i64> {
    let h = 32usize;
    let w = 32usize;
    let kh = 4usize;
    let kw = 4usize;
    let oh = h / kh;
    let ow = w / kw;
    let mut out = Vec::with_capacity(oh * ow);
    for i in 0..oh {
        for j in 0..ow {
            let mut s = 0i64;
            for ii in 0..kh {
                for jj in 0..kw {
                    s += after_conv[(i * kh + ii) * w + (j * kw + jj)];
                }
            }
            out.push(s * pool_inv_fp);
        }
    }
    out
}

fn quantize_fc_matrix(weight: &Array2<f64>) -> Vec<i32> {
    let flat: Vec<f64> = weight.iter().copied().collect();
    real_to_fixed_point(&flat, 16)
}

fn quantize_fc_bias(bias: &Array1<f64>) -> Vec<i32> {
    let flat: Vec<f64> = bias.iter().copied().collect();
    real_to_fixed_point(&flat, 16)
}

fn fc_matmul(row: &[i64], weight: &Array2<f64>, bias: &Array1<f64>) -> Vec<i64> {
    let wq = quantize_fc_matrix(weight);
    let bq = quantize_fc_bias(bias);
    let in_dim = row.len();
    let (rows, cols) = (weight.nrows(), weight.ncols());
    let (in_d, out_d) = if rows == in_dim {
        (rows, cols)
    } else {
        (cols, rows)
    };
    let mut out = vec![0i64; out_d];
    for j in 0..out_d {
        let mut acc = 0i64;
        for i in 0..in_d {
            let w = if rows == in_dim {
                wq[i * cols + j] as i64
            } else {
                wq[j * rows + i] as i64
            };
            acc += row[i] * w;
        }
        out[j] = acc + bq[j] as i64;
    }
    out
}

/// Run homomorphic-equivalent plain forward on one `(32×32)` fixed input (row-major).
pub fn numpy_homomorphic_plain(
    input_32x32: &[i32],
    weights: &NetworkAWeights,
    plan: &TruncationPlan,
) -> Result<PlainForwardLayers, String> {
    if input_32x32.len() != 32 * 32 {
        return Err(format!(
            "expected 32x32={}, got {}",
            32 * 32,
            input_32x32.len()
        ));
    }
    let after_conv = apply_client_action(
        &conv2d_int32(input_32x32, &CONV_FILTER)
            .into_iter()
            .map(|v| v as i64)
            .collect::<Vec<_>>(),
        ClientAction::Relu,
        None,
    )?;
    let pool_pre = pool_sum_fixed(&after_conv, plan.pool_inv_fp);
    let after_pool = apply_client_action(&pool_pre, ClientAction::Shift, Some(plan.shift_pool))?;
    let fc1_pre = fc_matmul(&after_pool, &weights.weight_fc1, &weights.bias_fc1);
    let after_fc1 = apply_client_action(&fc1_pre, ClientAction::ReluThenShift, Some(plan.shift_fc1))?;
    let fc2_pre = fc_matmul(&after_fc1, &weights.weight_fc2, &weights.bias_fc2);
    let after_fc2 = apply_client_action(&fc2_pre, ClientAction::ReluOnly, None)?;
    let prediction = after_fc2
        .iter()
        .enumerate()
        .max_by_key(|(_, v)| *v)
        .map(|(i, _)| i)
        .unwrap_or(0);
    Ok(PlainForwardLayers {
        after_fc2,
        prediction,
    })
}
