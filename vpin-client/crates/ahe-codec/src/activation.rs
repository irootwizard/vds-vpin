use crate::fixed::{fixed_point_to_real, real_to_fixed_point, CONV_RESCALE, FIXED_POINT_BITS};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClientAction {
    ConvRelu,
    Relu,
    Shift,
    ReluThenShift,
    ReluOnly,
    LogitsOnly,
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
    }
}
