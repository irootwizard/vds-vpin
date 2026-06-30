/// Homomorphic operations for LeNet AHE pipeline.
///
/// Conventions:
///   - All layer computations use weights at f=16 (real_to_fixed_point(..., 16)).
///   - Conv bias is encrypted at f=32 to match the conv output scale (f=16 × f=16 = f=32).
///   - FC bias is encrypted at f=32 for the same reason.
///   - The client's `relu_pool_shift` action handles 2×2 avg pool + shift 32→16.
///   - c3 is treated as FC(400→120) because the 5×5 input exactly matches the kernel.
use ahe_codec::{encrypt_scalar, real_to_fixed_point, PARALLEL_THRESHOLD};
use ahe_crypto_e2::{E2Point, KeyMaterial};
use ahe_model_bundle::{LeNetCifarWeights, LeNetMnistWeights};
use ndarray::Array4;
use num_bigint::BigUint;
use rand::Rng;
use rayon::prelude::*;

use crate::network_a::{track_add, track_mult};

type CtGrid = Vec<Vec<E2Point>>;
pub type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

// ---------------------------------------------------------------------------
// Bias encryption (at f=32 to match float-weight layer output scale)
// ---------------------------------------------------------------------------

fn encrypt_bias_f32<R: Rng>(
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
// General float-weight conv2d (no padding, stride=1)
// ---------------------------------------------------------------------------

/// Perform homomorphic conv2d with float weights on one (c_out, c_in) pair.
///
/// input_channel: &CtGrid of shape [H, W] (ciphertext at f=16)
/// kernel:        &[[f64; 5]; 5] fixed to 5×5
/// Returns:       CtGrid of shape [H-4, W-4] at f=32
fn lenet_conv2d_channel(
    input_channel: &CtGrid,
    kernel_fp: &[i64],    // flat 5×5 = 25 values at f=16
    identity: &E2Point,
) -> CtGrid {
    let ksize = 5usize;
    let h = input_channel.len();
    let w = input_channel[0].len();
    let oh = h - (ksize - 1);
    let ow = w - (ksize - 1);

    let flat: Vec<E2Point> = (0..oh * ow)
        .into_par_iter()
        .map(|idx| {
            let i = idx / ow;
            let j = idx % ow;
            let mut sum: Option<E2Point> = None;
            for ki in 0..ksize {
                for kj in 0..ksize {
                    let w_fp = kernel_fp[ki * ksize + kj];
                    if w_fp == 0 {
                        continue;
                    }
                    let term = input_channel[i + ki][j + kj].scalar_mul_i64(w_fp);
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

/// Homomorphic conv2d layer for LeNet (5×5 kernels, no padding, stride=1).
///
/// `weight`: Array4<f64> of shape (C_out, C_in, 5, 5)
/// `bias_c1/c2`: bias ciphertexts at f=32, shape [C_out]
/// Input c1/c2: Ct4 of shape [B, C_in, H, W] at f=16
/// Output: Ct4 of shape [B, C_out, H-4, W-4] at f=32
pub fn lenet_conv_ciphertext(
    c1: &Ct4,
    c2: &Ct4,
    weight: &Array4<f64>,
    bias_c1: &[E2Point],
    bias_c2: &[E2Point],
    identity: &E2Point,
) -> (Ct4, Ct4) {
    let batch = c1.len();
    let c_in = c1[0].len();
    let h = c1[0][0].len();
    let w = c1[0][0][0].len();
    let c_out = weight.shape()[0];
    let ksize = 5usize;
    let oh = h - (ksize - 1);
    let ow = w - (ksize - 1);

    // Pre-compute fixed-point kernels (at f=16)
    let kernels_fp: Vec<Vec<i64>> = (0..c_out)
        .map(|co| {
            (0..c_in)
                .flat_map(|ci| {
                    (0..ksize).flat_map(move |ki| {
                        (0..ksize).map(move |kj| {
                            let flat_w: Vec<f64> = vec![weight[[co, ci, ki, kj]]];
                            real_to_fixed_point(&flat_w, 16)[0] as i64
                        })
                    })
                })
                .collect()
        })
        .collect();

    let mut o1 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; c_out]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; c_out]; batch];

    for b in 0..batch {
        // For each output channel: sum contributions from all input channels
        let results: Vec<(CtGrid, CtGrid)> = (0..c_out)
            .into_par_iter()
            .map(|co| {
                let mut acc1: Option<CtGrid> = None;
                let mut acc2: Option<CtGrid> = None;
                for ci in 0..c_in {
                    // kernel slice for this (co, ci) pair: 25 values at f=16
                    let k_offset = ci * ksize * ksize;
                    let k_flat = &kernels_fp[co][k_offset..k_offset + ksize * ksize];

                    let part1 = lenet_conv2d_channel(&c1[b][ci], k_flat, identity);
                    let part2 = lenet_conv2d_channel(&c2[b][ci], k_flat, identity);

                    acc1 = Some(match acc1 {
                        None => part1,
                        Some(a) => pointwise_add_grid(&a, &part1),
                    });
                    acc2 = Some(match acc2 {
                        None => part2,
                        Some(a) => pointwise_add_grid(&a, &part2),
                    });
                }
                // Add bias (at f=32)
                let mut r1 = acc1.unwrap_or_else(|| vec![vec![E2Point::Identity; ow]; oh]);
                let mut r2 = acc2.unwrap_or_else(|| vec![vec![E2Point::Identity; ow]; oh]);
                for i in 0..oh {
                    for j in 0..ow {
                        r1[i][j] = r1[i][j].add(&bias_c1[co]);
                        r2[i][j] = r2[i][j].add(&bias_c2[co]);
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
// Flatten 4D ciphertext to 2D (batch=1)
// ---------------------------------------------------------------------------

pub fn lenet_flatten(c1: &Ct4, c2: &Ct4) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let c_out = c1[0].len();
    let oh = c1[0][0].len();
    let ow = c1[0][0][0].len();
    let n = c_out * oh * ow;
    let mut f1 = vec![vec![E2Point::Identity; n]; 1];
    let mut f2 = vec![vec![E2Point::Identity; n]; 1];
    let mut idx = 0;
    for c in 0..c_out {
        for i in 0..oh {
            for j in 0..ow {
                f1[0][idx] = c1[0][c][i][j].clone();
                f2[0][idx] = c2[0][c][i][j].clone();
                idx += 1;
            }
        }
    }
    (f1, f2)
}

// ---------------------------------------------------------------------------
// Generic FC layer (reused for c3/fc4/fc5)
// ---------------------------------------------------------------------------

fn lenet_fc(
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

// ---------------------------------------------------------------------------
// Public layer wrappers for LeNet-MNIST
// ---------------------------------------------------------------------------

pub fn lenet_mnist_conv1<R: Rng>(
    w: &LeNetMnistWeights,
    c1: &Ct4,
    c2: &Ct4,
    keys: &KeyMaterial,
    rng: &mut R,
    identity: &E2Point,
) -> (Ct4, Ct4) {
    let bias: Vec<f64> = w.conv1_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_conv_ciphertext(c1, c2, &w.conv1_weight, &bc1, &bc2, identity)
}

pub fn lenet_mnist_conv2<R: Rng>(
    w: &LeNetMnistWeights,
    c1: &Ct4,
    c2: &Ct4,
    keys: &KeyMaterial,
    rng: &mut R,
    identity: &E2Point,
) -> (Ct4, Ct4) {
    let bias: Vec<f64> = w.conv2_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_conv_ciphertext(c1, c2, &w.conv2_weight, &bc1, &bc2, identity)
}

pub fn lenet_mnist_c3<R: Rng>(
    w: &LeNetMnistWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.c3_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.c3_weight, &bc1, &bc2)
}

pub fn lenet_mnist_fc4<R: Rng>(
    w: &LeNetMnistWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.fc4_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.fc4_weight, &bc1, &bc2)
}

pub fn lenet_mnist_fc5<R: Rng>(
    w: &LeNetMnistWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.fc5_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.fc5_weight, &bc1, &bc2)
}

// ---------------------------------------------------------------------------
// Public layer wrappers for LeNet-CIFAR10
// ---------------------------------------------------------------------------

pub fn lenet_cifar_conv1<R: Rng>(
    w: &LeNetCifarWeights,
    c1: &Ct4,
    c2: &Ct4,
    keys: &KeyMaterial,
    rng: &mut R,
    identity: &E2Point,
) -> (Ct4, Ct4) {
    let bias: Vec<f64> = w.conv1_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_conv_ciphertext(c1, c2, &w.conv1_weight, &bc1, &bc2, identity)
}

pub fn lenet_cifar_conv2<R: Rng>(
    w: &LeNetCifarWeights,
    c1: &Ct4,
    c2: &Ct4,
    keys: &KeyMaterial,
    rng: &mut R,
    identity: &E2Point,
) -> (Ct4, Ct4) {
    let bias: Vec<f64> = w.conv2_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_conv_ciphertext(c1, c2, &w.conv2_weight, &bc1, &bc2, identity)
}

pub fn lenet_cifar_c3<R: Rng>(
    w: &LeNetCifarWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.c3_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.c3_weight, &bc1, &bc2)
}

pub fn lenet_cifar_fc4<R: Rng>(
    w: &LeNetCifarWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.fc4_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.fc4_weight, &bc1, &bc2)
}

pub fn lenet_cifar_fc5<R: Rng>(
    w: &LeNetCifarWeights,
    c1: &[Vec<E2Point>],
    c2: &[Vec<E2Point>],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = w.fc5_bias.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias_f32(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    lenet_fc(c1, c2, &w.fc5_weight, &bc1, &bc2)
}
