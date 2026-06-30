use ahe_codec::{encrypt_scalar, real_to_fixed_point, PARALLEL_THRESHOLD};
use ahe_crypto_e2::{E2Point, KeyMaterial};
use ahe_model_bundle::{NetworkAWeights, CONV_FILTER};
use num_bigint::BigUint;
use rand::Rng;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) static PT_MULT: AtomicU64 = AtomicU64::new(0);
pub(crate) static PT_ADD: AtomicU64 = AtomicU64::new(0);

pub fn reset_op_counters() {
    PT_MULT.store(0, Ordering::Relaxed);
    PT_ADD.store(0, Ordering::Relaxed);
}

pub fn get_op_counters() -> (u64, u64) {
    (PT_ADD.load(Ordering::Relaxed), PT_MULT.load(Ordering::Relaxed))
}

pub(crate) fn track_mult() { PT_MULT.fetch_add(1, Ordering::Relaxed); }
pub(crate) fn track_add() { PT_ADD.fetch_add(1, Ordering::Relaxed); }

type CtGrid = Vec<Vec<E2Point>>;
pub type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

fn my_conv2d(input: &CtGrid, filter: &[[i64; 3]; 3], identity: &E2Point) -> CtGrid {
    let h = input.len();
    let w = input[0].len();
    let pad = 1usize;
    let mut padded = vec![vec![E2Point::Identity; w + 2 * pad]; h + 2 * pad];
    for i in 0..h {
        for j in 0..w {
            padded[i + pad][j + pad] = input[i][j].clone();
        }
    }
    let flat: Vec<E2Point> = (0..h * w)
        .into_par_iter()
        .map(|idx| {
            let i = idx / w;
            let j = idx % w;
            let mut sum: Option<E2Point> = None;
            for ii in 0..3 {
                for jj in 0..3 {
                    let wgt = filter[ii][jj];
                    if wgt == 0 {
                        continue;
                    }
                    let term = padded[i + ii][j + jj].scalar_mul_i64(wgt);
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
    let mut out = vec![vec![E2Point::Identity; w]; h];
    for i in 0..h {
        for j in 0..w {
            out[i][j] = flat[i * w + j].clone();
        }
    }
    out
}

pub fn conv2_ciphertext(c1: &[Vec<Vec<Vec<E2Point>>>], c2: &[Vec<Vec<Vec<E2Point>>>], identity: &E2Point) -> (Ct4, Ct4) {
    let batch = c1.len();
    let ch = c1[0].len();
    let h = c1[0][0].len();
    let w = c1[0][0][0].len();
    let mut o1 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; w]; h]; ch]; batch];
    for b in 0..batch {
        let (c1s, c2s): (Vec<_>, Vec<_>) = (0..ch)
            .into_par_iter()
            .map(|c| {
                (
                    my_conv2d(&c1[b][c], &CONV_FILTER, identity),
                    my_conv2d(&c2[b][c], &CONV_FILTER, identity),
                )
            })
            .unzip();
        for c in 0..ch {
            o1[b][c] = c1s[c].clone();
            o2[b][c] = c2s[c].clone();
        }
    }
    (o1, o2)
}

fn my_avg_pool2d(input: &CtGrid, identity: &E2Point, kernel: usize, stride: usize) -> CtGrid {
    let h = input.len();
    let w = input[0].len();
    let oh = (h - kernel) / stride + 1;
    let ow = (w - kernel) / stride + 1;
    let inv_fp = real_to_fixed_point(&[1.0 / (kernel * kernel) as f64], 10)[0] as i64;
    let mut out = vec![vec![E2Point::Identity; ow]; oh];
    out.par_iter_mut().enumerate().for_each(|(i, row)| {
        for j in 0..ow {
            let mut sum: Option<E2Point> = None;
            for ii in 0..kernel {
                for jj in 0..kernel {
                    let cell = input[i * stride + ii][j * stride + jj].clone();
                    sum = Some(match sum {
                        None => cell,
                        Some(s) => {
                            track_add();
                            s.add(&cell)
                        }
                    });
                }
            }
            let s = sum.unwrap_or_else(|| identity.clone());
            track_mult();
            row[j] = s.scalar_mul_i64(inv_fp);
        }
    });
    out
}

pub fn avg_pool_ciphertext(c1: &[Vec<Vec<Vec<E2Point>>>], c2: &[Vec<Vec<Vec<E2Point>>>], identity: &E2Point, kernel: usize, stride: usize) -> (Ct4, Ct4) {
    let batch = c1.len();
    let ch = c1[0].len();
    let oh = c1[0][0].len() / kernel;
    let ow = c1[0][0][0].len() / kernel;
    let mut o1 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; ch]; batch];
    let mut o2 = vec![vec![vec![vec![E2Point::Identity; ow]; oh]; ch]; batch];
    for b in 0..batch {
        let (p1, p2): (Vec<_>, Vec<_>) = (0..ch)
            .into_par_iter()
            .map(|c| {
                (
                    my_avg_pool2d(&c1[b][c], identity, kernel, stride),
                    my_avg_pool2d(&c2[b][c], identity, kernel, stride),
                )
            })
            .unzip();
        for c in 0..ch {
            o1[b][c] = p1[c].clone();
            o2[b][c] = p2[c].clone();
        }
    }
    (o1, o2)
}

pub fn flatten_ciphertext(c1: &[Vec<Vec<Vec<E2Point>>>], c2: &[Vec<Vec<Vec<E2Point>>>]) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let ch = c1[0].len();
    let h = c1[0][0].len();
    let w = c1[0][0][0].len();
    let n = ch * h * w;
    let mut f1 = vec![vec![E2Point::Identity; n]; 1];
    let mut f2 = vec![vec![E2Point::Identity; n]; 1];
    let mut idx = 0;
    for c in 0..ch {
        for i in 0..h {
            for j in 0..w {
                f1[0][idx] = c1[0][c][i][j].clone();
                f2[0][idx] = c2[0][c][i][j].clone();
                idx += 1;
            }
        }
    }
    (f1, f2)
}

fn encrypt_bias<R: Rng>(bias: &[f64], generator: &E2Point, public_key: &E2Point, order: &BigUint, rng: &mut R) -> (Vec<E2Point>, Vec<E2Point>) {
    let fixed = real_to_fixed_point(bias, 16);
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

fn fc_layer(in_c1: &[Vec<E2Point>], in_c2: &[Vec<E2Point>], weights: &ndarray::Array2<f64>, bias_c1: &[E2Point], bias_c2: &[E2Point]) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let flat_w: Vec<f64> = weights.iter().copied().collect();
    let weight_fp = real_to_fixed_point(&flat_w, 16);
    let rows = in_c1[0].len();
    let cols = weights.ncols();
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
                let term1 = in_c1[0][i].scalar_mul_i64(w);
                let term2 = in_c2[0][i].scalar_mul_i64(w);
                track_mult();
                acc1 = Some(match acc1 {
                    None => term1,
                    Some(a) => {
                        track_add();
                        a.add(&term1)
                    }
                });
                acc2 = Some(match acc2 {
                    None => term2,
                    Some(a) => {
                        track_add();
                        a.add(&term2)
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

pub fn fc1_layer<R: Rng>(weights: &NetworkAWeights, c1: &[Vec<E2Point>], c2: &[Vec<E2Point>], keys: &KeyMaterial, rng: &mut R) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = weights.bias_fc1.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    fc_layer(c1, c2, &weights.weight_fc1, &bc1, &bc2)
}

pub fn fc2_layer<R: Rng>(weights: &NetworkAWeights, c1: &[Vec<E2Point>], c2: &[Vec<E2Point>], keys: &KeyMaterial, rng: &mut R) -> (Vec<Vec<E2Point>>, Vec<Vec<E2Point>>) {
    let bias: Vec<f64> = weights.bias_fc2.iter().copied().collect();
    let (bc1, bc2) = encrypt_bias(&bias, &keys.generator, &keys.public_key, &keys.curve_order, rng);
    fc_layer(c1, c2, &weights.weight_fc2, &bc1, &bc2)
}
