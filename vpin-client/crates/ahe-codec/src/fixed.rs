pub const FIXED_POINT_BITS: u32 = 16;
pub const CONV_RESCALE: i64 = 1 << FIXED_POINT_BITS;

pub fn real_to_fixed_point(values: &[f64], bits: u32) -> Vec<i32> {
    let scale = 2f64.powi(bits as i32);
    values.iter().map(|v| (v * scale) as i32).collect()
}

pub fn fixed_point_to_real(values: &[i64], bits: u32) -> Vec<f32> {
    let scale = 2f64.powi(bits as i32);
    values.iter().map(|v| (*v as f64 / scale) as f32).collect()
}
