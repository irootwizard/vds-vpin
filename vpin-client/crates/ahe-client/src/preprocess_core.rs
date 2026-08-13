//! Shared Network-A input preprocess (pad 32×32, per-image min-max, Q16 fixed).

pub const PAD: usize = 32;
pub const FP_SCALE: f32 = 65536.0;

#[derive(Clone, Debug)]
pub struct PreprocessStages {
    pub raw_uint8: [u8; 784],
    pub padded: Vec<f32>,
    pub normalized: Vec<f32>,
    pub fixed: Vec<i32>,
}

pub fn preprocess_uint8_28x28(raw: &[u8; 784]) -> PreprocessStages {
    let mut x_f = [0f32; 784];
    for (i, &px) in raw.iter().enumerate() {
        x_f[i] = px as f32 / 255.0;
    }
    let padded = pad_to_32x32(&x_f);
    let normalized = min_max_scale(&padded);
    let fixed: Vec<i32> = normalized
        .iter()
        .map(|v| (v * FP_SCALE).round() as i32)
        .collect();
    PreprocessStages {
        raw_uint8: *raw,
        padded,
        normalized,
        fixed,
    }
}

pub fn pad_to_32x32(x: &[f32; 784]) -> Vec<f32> {
    let mut out = vec![0f32; PAD * PAD];
    for r in 0..28 {
        for c in 0..28 {
            out[(r + 2) * PAD + (c + 2)] = x[r * 28 + c];
        }
    }
    out
}

pub fn min_max_scale(data: &[f32]) -> Vec<f32> {
    let mut min = f32::INFINITY;
    let mut max = f32::NEG_INFINITY;
    for &v in data {
        min = min.min(v);
        max = max.max(v);
    }
    if (max - min).abs() < 1e-12 {
        return vec![0.5; data.len()];
    }
    data.iter()
        .map(|v| ((v - min) / (max - min)).clamp(0.0, 1.0))
        .collect()
}

pub fn input_digest_hex(fixed: &[i32]) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    for v in fixed {
        hasher.update(v.to_le_bytes());
    }
    hex::encode(hasher.finalize())
}
