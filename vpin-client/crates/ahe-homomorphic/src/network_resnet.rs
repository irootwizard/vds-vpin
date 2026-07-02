/// Homomorphic operations for ResNet18 AHE pipeline.
///
/// Fixed-point protocol:
///   - Input to each block: f=16 (re-encrypted after client relu_then_shift)
///   - Conv output (f=32): client decrypts, ReLU, shift 32→16, re-encrypts
///   - Identity shortcut: server multiplies block-input ciphertext by 2^16 to
///     align f=16 → f=32, then adds to conv2 output (f=32)
///   - Downsample shortcut: server runs 1×1 ds_conv (folded) on block input
///     (f=16→f=32), holds the ciphertext, adds to conv2 output (both f=32)
///   - Final: AvgPool(4×4) + Linear(512→10) merged on server (both linear)
use ahe_codec::{encrypt_scalar, real_to_fixed_point, PARALLEL_THRESHOLD};
use ahe_crypto_e2::{E2Point, KeyMaterial};
use ndarray::Array4;
use num_bigint::BigUint;
use rand::Rng;
use rayon::prelude::*;

use crate::network_a::{track_add, track_mult};

type CtGrid = Vec<Vec<E2Point>>;
pub type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

const SCALE_16: i64 = (1 << 16) as i64;

// ---------------------------------------------------------------------------
// Bias encryption at f=32
// ---------------------------------------------------------------------------

pub fn encrypt_bias_f32<R: Rng>(
    bias: &[f64],
    generator: &E2Point,
    public_key: &E2Point,
    order: &BigUint,
    rng: &mut R,
) -> (Vec<E2Point>, Vec<E2Point>) {
    let fixed = real_to_fixed_point(bias, 32);
    if fixed.len() >= PARALLEL_THRESHOLD {
        let order = order.clone();
        let g = generator.clone();
        let pk = public_key.clone();
        let cts: Vec<_> = fixed
            .par_iter()
            .map(|&b| {
                let mut local = rand::thread_rng();
                encrypt_scalar(b as i64, &g, &pk, &order, &mut local)
            })
            .collect();
        let c1 = cts.iter().map(|c| c.c1.clone()).collect();
        let c2 = cts.iter().map(|c| c.c2.clone()).collect();
        (c1, c2)
    } else {
        let mut c1 = Vec::with_capacity(fixed.len());
        let mut c2 = Vec::with_capacity(fixed.len());
        for &b in &fixed {
            let ct = encrypt_scalar(b as i64, generator, public_key, order, rng);
            c1.push(ct.c1);
            c2.push(ct.c2);
        }
        (c1, c2)
    }
}

// ---------------------------------------------------------------------------
// General single-channel conv2d (configurable padding / stride)
// ---------------------------------------------------------------------------

fn resnet_conv2d_channel(
    input_channel: &CtGrid,
    kernel_fp: &[i64],
    identity: &E2Point,
    padding: usize,
    stride: usize,
    kernel_size: usize,
) -> CtGrid {
    let h = input_channel.len();
    let w = input_channel[0].len();
    let oh = (h + 2 * padding - kernel_size) / stride + 1;
    let ow = (w + 2 * padding - kernel_size) / stride + 1;

    let padded_h = h + 2 * padding;
    let padded_w = w + 2 * padding;
    let mut padded = vec![vec![E2Point::Identity; padded_w]; padded_h];
    for i in 0..h {
        for j in 0..w {
            padded[i + padding][j + padding] = input_channel[i][j].clone();
        }
    }

    let flat: Vec<E2Point> = (0..oh * ow)
        .into_par_iter()
        .map(|idx| {
            let i = idx / ow;
            let j = idx % ow;
            let mut sum: Option<E2Point> = None;
            for ki in 0..kernel_size {
                for kj in 0..kernel_size {
                    let w_fp = kernel_fp[ki * kernel_size + kj];
                    if w_fp == 0 {
                        continue;
                    }
                    let term = padded[i * stride + ki][j * stride + kj].scalar_mul_i64(w_fp);
                    track_mult();
                    sum = Some(match sum {
                        None => term,
                        Some(s) => {
                            track_add();
                            s.add(&term)
                        }
                    });
                }
            }
            sum.unwrap_or_else(|| identity.clone())
        })
        .collect();

    let mut out = vec![vec![E2Point::Identity; ow]; oh];
    for i in 0..oh {
        for j in 0..ow {
            out[i][j] = flat[i * ow + j].clone();
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Multi-channel conv ciphertext
// ---------------------------------------------------------------------------

pub fn resnet_conv_ciphertext(
    c1: &Ct4,
    c2: &Ct4,
    weight: &Array4<f64>,
    bias_c1: &[E2Point],
    bias_c2: &[E2Point],
    identity: &E2Point,
    padding: usize,
    stride: usize,
) -> (Ct4, Ct4) {
    let batch = c1.len();
    let c_in = c1[0].len();
    let h = c1[0][0].len();
    let w = c1[0][0][0].len();
    let c_out = weight.shape()[0];
    let ksize = weight.shape()[2]; // kernel height (3 for 3×3, 1 for 1×1 ds conv)
    let oh = (h + 2 * padding - ksize) / stride + 1;
    let ow = (w + 2 * padding - ksize) / stride + 1;

    let kernels_fp: Vec<Vec<i64>> = (0..c_out)
        .map(|co| {
            let flat_w: Vec<f64> = (0..c_in)
                .flat_map(|ci| (0..ksize).flat_map(move |ki| (0..ksize).map(move |kj| weight[[co, ci, ki, kj]])))
                .collect();
            real_to_fixed_point(&flat_w, 16)
                .into_iter()
                .map(|v| v as i64)
                .collect()
        })
        .collect();

    let mut o1 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; c_out]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; c_out]; batch];

    for b in 0..batch {
        let results: Vec<(CtGrid, CtGrid)> = (0..c_out)
            .into_par_iter()
            .map(|co| {
                let mut acc1: Option<CtGrid> = None;
                let mut acc2: Option<CtGrid> = None;
                for ci in 0..c_in {
                    let k_offset = ci * ksize * ksize;
                    let k_flat = &kernels_fp[co][k_offset..k_offset + ksize * ksize];
                    let part1 = resnet_conv2d_channel(&c1[b][ci], k_flat, identity, padding, stride, ksize);
                    let part2 = resnet_conv2d_channel(&c2[b][ci], k_flat, identity, padding, stride, ksize);
                    acc1 = Some(match acc1 {
                        None => part1,
                        Some(a) => pointwise_add_grid(&a, &part1),
                    });
                    acc2 = Some(match acc2 {
                        None => part2,
                        Some(a) => pointwise_add_grid(&a, &part2),
                    });
                }
                let mut r1 = acc1.unwrap_or_else(|| vec![vec![E2Point::Identity; ow]; oh]);
                let mut r2 = acc2.unwrap_or_else(|| vec![vec![E2Point::Identity; ow]; oh]);
                for y in 0..oh {
                    for x in 0..ow {
                        r1[y][x] = r1[y][x].add(&bias_c1[co]);
                        r2[y][x] = r2[y][x].add(&bias_c2[co]);
                        track_add();
                    }
                }
                (r1, r2)
            })
            .collect();
        for (co, (r1, r2)) in results.into_iter().enumerate() {
            o1[b][co] = r1;
            o2[b][co] = r2;
        }
    }
    (o1, o2)
}

fn pointwise_add_grid(a: &CtGrid, b: &CtGrid) -> CtGrid {
    let h = a.len();
    let w = a[0].len();
    let mut out = vec![vec![E2Point::Identity; w]; h];
    for i in 0..h {
        for j in 0..w {
            out[i][j] = a[i][j].add(&b[i][j]);
            track_add();
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Shortcut additions
// ---------------------------------------------------------------------------

pub fn resnet_add_identity_shortcut(
    c1_main: &Ct4,
    c2_main: &Ct4,
    c1_sc: &Ct4,
    c2_sc: &Ct4,
) -> (Ct4, Ct4) {
    let batch = c1_main.len();
    let ch = c1_main[0].len();
    let h = c1_main[0][0].len();
    let w = c1_main[0][0][0].len();
    let mut o1 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    for b in 0..batch {
        let (r1, r2): (Vec<_>, Vec<_>) = (0..ch)
            .into_par_iter()
            .map(|c| {
                let mut ch1 = vec![vec![E2Point::Identity; w]; h];
                let mut ch2 = vec![vec![E2Point::Identity; w]; h];
                for y in 0..h {
                    for x in 0..w {
                        let scaled = c1_sc[b][c][y][x].scalar_mul_i64(SCALE_16);
                        track_mult();
                        ch1[y][x] = c1_main[b][c][y][x].add(&scaled);
                        let scaled = c2_sc[b][c][y][x].scalar_mul_i64(SCALE_16);
                        track_mult();
                        ch2[y][x] = c2_main[b][c][y][x].add(&scaled);
                        track_add();
                    }
                }
                (ch1, ch2)
            })
            .unzip();
        for c in 0..ch {
            o1[b][c] = r1[c].clone();
            o2[b][c] = r2[c].clone();
        }
    }
    (o1, o2)
}

pub fn resnet_add_ds_shortcut(
    c1_main: &Ct4,
    c2_main: &Ct4,
    c1_ds: &Ct4,
    c2_ds: &Ct4,
) -> (Ct4, Ct4) {
    let batch = c1_main.len();
    let ch = c1_main[0].len();
    let h = c1_main[0][0].len();
    let w = c1_main[0][0][0].len();
    let mut o1 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    for b in 0..batch {
        let (r1, r2): (Vec<_>, Vec<_>) = (0..ch)
            .into_par_iter()
            .map(|c| {
                let mut ch1 = vec![vec![E2Point::Identity; w]; h];
                let mut ch2 = vec![vec![E2Point::Identity; w]; h];
                for y in 0..h {
                    for x in 0..w {
                        ch1[y][x] = c1_main[b][c][y][x].add(&c1_ds[b][c][y][x]);
                        ch2[y][x] = c2_main[b][c][y][x].add(&c2_ds[b][c][y][x]);
                        track_add();
                    }
                }
                (ch1, ch2)
            })
            .unzip();
        for c in 0..ch {
            o1[b][c] = r1[c].clone();
            o2[b][c] = r2[c].clone();
        }
    }
    (o1, o2)
}

// ---------------------------------------------------------------------------
// AvgPool(4×4) + Linear(512→10) merged
// ---------------------------------------------------------------------------

pub fn resnet_avgpool_fc<R: Rng>(
    c1: &Ct4,
    c2: &Ct4,
    linear_w: &ndarray::Array2<f64>,
    linear_b: &ndarray::Array1<f64>,
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let _batch = c1.len();
    let ch = c1[0].len();
    let h = c1[0][0].len();
    let w = c1[0][0][0].len();
    let pool_kernel = h; // global avg pool: kernel = spatial size

    let inv_fp = real_to_fixed_point(&[1.0 / (pool_kernel * pool_kernel) as f64], 6)[0] as i64;

    // Pool each channel to [1,1] then flatten to [1, ch]
    let mut pool_c1 = Vec::with_capacity(ch);
    let mut pool_c2 = Vec::with_capacity(ch);
    for c in 0..ch {
        let mut sum1: Option<E2Point> = None;
        let mut sum2: Option<E2Point> = None;
        for y in 0..h {
            for x in 0..w {
                sum1 = Some(match sum1 {
                    None => c1[0][c][y][x].clone(),
                    Some(s) => {
                        track_add();
                        s.add(&c1[0][c][y][x])
                    }
                });
                sum2 = Some(match sum2 {
                    None => c2[0][c][y][x].clone(),
                    Some(s) => {
                        track_add();
                        s.add(&c2[0][c][y][x])
                    }
                });
            }
        }
        let avg1 = sum1.unwrap_or(E2Point::Identity).scalar_mul_i64(inv_fp);
        let avg2 = sum2.unwrap_or(E2Point::Identity).scalar_mul_i64(inv_fp);
        track_mult();
        pool_c1.push(avg1);
        pool_c2.push(avg2);
    }

    let flat_c1 = vec![pool_c1];
    let flat_c2 = vec![pool_c2];

    // Linear(512→10)
    let bias: Vec<f64> = linear_b.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);

    resnet_fc(&flat_c1, &flat_c2, linear_w, &bc1, &bc2)
}

fn resnet_fc(
    in_c1: &[Vec<E2Point>],
    in_c2: &[Vec<E2Point>],
    weight: &ndarray::Array2<f64>,
    bias_c1: &[E2Point],
    bias_c2: &[E2Point],
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let flat_w: Vec<f64> = weight.iter().copied().collect();
    let weight_fp = real_to_fixed_point(&flat_w, 16);
    let rows = in_c1[0].len();
    let cols = weight.ncols();

    let cols_out: Vec<(E2Point, E2Point)> = (0..cols)
        .into_par_iter()
        .map(|j| {
            let mut acc1: Option<E2Point> = None;
            let mut acc2: Option<E2Point> = None;
            for i in 0..rows {
                let w = weight_fp[i * cols + j] as i64;
                if w == 0 {
                    continue;
                }
                let t1 = in_c1[0][i].scalar_mul_i64(w);
                let t2 = in_c2[0][i].scalar_mul_i64(w);
                track_mult();
                acc1 = Some(match acc1 {
                    None => t1,
                    Some(a) => {
                        track_add();
                        a.add(&t1)
                    }
                });
                acc2 = Some(match acc2 {
                    None => t2,
                    Some(a) => {
                        track_add();
                        a.add(&t2)
                    }
                });
            }
            let mut o1 = acc1.unwrap_or(E2Point::Identity);
            let mut o2 = acc2.unwrap_or(E2Point::Identity);
            o1 = o1.add(&bias_c1[j]);
            o2 = o2.add(&bias_c2[j]);
            track_add();
            (o1, o2)
        })
        .collect();

    let mut out1 = vec![vec![E2Point::Identity; cols]; 1];
    let mut out2 = vec![vec![E2Point::Identity; cols]; 1];
    for (j, (a, b)) in cols_out.into_iter().enumerate() {
        out1[0][j] = a;
        out2[0][j] = b;
    }
    (out1, out2)
}
