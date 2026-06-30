use crate::fixed::{fixed_point_to_real, real_to_fixed_point, CONV_RESCALE, FIXED_POINT_BITS};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClientAction {
    ConvRelu,
    Relu,
    Shift,
    ReluThenShift,
    ReluOnly,
    LogitsOnly,
    /// Decrypt → relu → 2-D avg pool → shift to f=16.
    /// Extra parameters (pool_kernel, input_shape) are passed separately
    /// to `apply_relu_pool_shift`; this variant is used purely for dispatch.
    ReluPoolShift,
}

impl ClientAction {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "conv_relu" => Some(Self::ConvRelu),
            "relu" => Some(Self::Relu),
            "shift" => Some(Self::Shift),
            "relu_then_shift" => Some(Self::ReluThenShift),
            "relu_only" => Some(Self::ReluOnly),
            "logits_only" => Some(Self::LogitsOnly),
            "relu_pool_shift" => Some(Self::ReluPoolShift),
            _ => None,
        }
    }
}

pub fn relu(values: &[i64]) -> Vec<i64> {
    values.iter().map(|&v| v.max(0)).collect()
}

pub fn shifting(decrypted: &[i64], from_bits: u32, to_bits: u32) -> Vec<i32> {
    let reals = fixed_point_to_real(decrypted, from_bits);
    real_to_fixed_point(
        &reals.iter().map(|&r| r as f64).collect::<Vec<_>>(),
        to_bits,
    )
}

pub fn apply_client_action(
    decrypted: &[i64],
    action: ClientAction,
    shift_bits: Option<u32>,
) -> Result<Vec<i64>, String> {
    match action {
        ClientAction::ConvRelu => Ok(relu(
            &decrypted
                .iter()
                .map(|&v| v.div_euclid(CONV_RESCALE))
                .collect::<Vec<_>>(),
        )),
        ClientAction::Relu => Ok(relu(decrypted)),
        ClientAction::Shift => {
            let bits = shift_bits.ok_or("shift_bits required")?;
            Ok(shifting(decrypted, bits, FIXED_POINT_BITS)
                .into_iter()
                .map(|v| v as i64)
                .collect())
        }
        ClientAction::ReluThenShift => {
            let bits = shift_bits.ok_or("shift_bits required")?;
            let r = relu(decrypted);
            Ok(shifting(&r, bits, FIXED_POINT_BITS)
                .into_iter()
                .map(|v| v as i64)
                .collect())
        }
        ClientAction::ReluOnly => Ok(relu(decrypted)),
        ClientAction::LogitsOnly => Ok(decrypted.to_vec()),
        // ReluPoolShift requires extra args; call apply_relu_pool_shift directly.
        ClientAction::ReluPoolShift => Err(
            "ReluPoolShift requires pool_kernel and input_shape; call apply_relu_pool_shift()".into(),
        ),
    }
}

/// Applies relu → 2-D avg pool → shift for the LeNet conv phases.
///
/// `decrypted`:   flat i64 array at scale f=shift_bits (typically 32)
/// `input_shape`: [B, C, H, W] — shape of the tensor as sent by the server
/// `pool_kernel`: pool window size (2 for LeNet's 2×2 avg pool)
/// `shift_bits`:  current scale (32), shifts down to FIXED_POINT_BITS (16)
///
/// Returns flattened re-encoded values at f=16 (i64 castable to i32).
pub fn apply_relu_pool_shift(
    decrypted: &[i64],
    input_shape: &[usize],   // [B, C, H, W]
    pool_kernel: usize,
    shift_bits: u32,
) -> Result<Vec<i64>, String> {
    if input_shape.len() != 4 {
        return Err(format!("input_shape must be 4-D, got {:?}", input_shape));
    }
    let b = input_shape[0];
    let c = input_shape[1];
    let h = input_shape[2];
    let w = input_shape[3];
    let expected = b * c * h * w;
    if decrypted.len() != expected {
        return Err(format!(
            "decrypted length {} != product of input_shape {:?} = {}",
            decrypted.len(), input_shape, expected
        ));
    }

    // Step 1: relu in-place (flat)
    let after_relu: Vec<i64> = decrypted.iter().map(|&v| v.max(0)).collect();

    // Step 2: reshape to [B, C, H, W] and apply 2-D avg pool
    let oh = h / pool_kernel;
    let ow = w / pool_kernel;
    let pool_size = (pool_kernel * pool_kernel) as i64;
    let mut pooled: Vec<i64> = Vec::with_capacity(b * c * oh * ow);

    for bi in 0..b {
        for ci in 0..c {
            for pi in 0..oh {
                for pj in 0..ow {
                    let mut sum = 0i64;
                    for ki in 0..pool_kernel {
                        for kj in 0..pool_kernel {
                            let hi = pi * pool_kernel + ki;
                            let wj = pj * pool_kernel + kj;
                            let flat_idx = bi * (c * h * w) + ci * (h * w) + hi * w + wj;
                            sum += after_relu[flat_idx];
                        }
                    }
                    pooled.push(sum / pool_size);
                }
            }
        }
    }

    // Step 3: shift from f=shift_bits to f=FIXED_POINT_BITS
    Ok(shifting(&pooled, shift_bits, FIXED_POINT_BITS)
        .into_iter()
        .map(|v| v as i64)
        .collect())
}
