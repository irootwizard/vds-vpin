//! CIFAR-10 RGB preprocess — mirrors A_cifar_rgb (F=16, per-image min-max).

pub const CIFAR_SIDE: usize = 32;
pub const CIFAR_CHW: usize = 3 * CIFAR_SIDE * CIFAR_SIDE;
pub const FP_SCALE: f64 = 65536.0;
pub const EPS_MIN: f64 = 0.001;
pub const EPS_MAX: f64 = 0.9999999;

#[derive(Clone, Debug)]
pub struct CifarPreprocessStages {
    pub raw_chw: [u8; CIFAR_CHW],
    pub normalized: Vec<f32>,
    pub fixed: Vec<i32>,
}

/// `raw` is CHW uint8 (3×32×32).
pub fn preprocess_cifar_rgb_chw(raw: &[u8; CIFAR_CHW]) -> CifarPreprocessStages {
    let mut x = [0f64; CIFAR_CHW];
    for (i, &px) in raw.iter().enumerate() {
        x[i] = px as f64 / 255.0;
    }
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    for &v in &x {
        min = min.min(v);
        max = max.max(v);
    }
    let denom = if (max - min).abs() < 1e-12 { 1.0 } else { max - min };
    let normalized: Vec<f32> = x
        .iter()
        .map(|v| (((v - min) / denom).clamp(EPS_MIN, EPS_MAX)) as f32)
        .collect();
    let fixed: Vec<i32> = normalized
        .iter()
        .map(|v| (v * FP_SCALE as f32).floor() as i32)
        .collect();
    CifarPreprocessStages {
        raw_chw: *raw,
        normalized,
        fixed,
    }
}

pub fn cifar_input_digest_hex(fixed: &[i32]) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    for v in fixed {
        hasher.update(v.to_le_bytes());
    }
    hex::encode(hasher.finalize())
}
