use ahe_crypto_e2::{CurveE2, E2Point, KeyMaterial};
use num_bigint::BigUint;
use num_traits::One;
use rand::Rng;
use rayon::prelude::*;

use crate::bsgs::BsgsTable;
use crate::fixed::FIXED_POINT_BITS;

/// Minimum tensor length before switching to rayon parallel encrypt/decrypt.
pub const PARALLEL_THRESHOLD: usize = 64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Ciphertext {
    pub c1: E2Point,
    pub c2: E2Point,
}

pub fn encrypt_scalar<R: Rng>(
    plaintext: i64,
    generator: &E2Point,
    public_key: &E2Point,
    curve_order: &BigUint,
    rng: &mut R,
) -> Ciphertext {
    let max = curve_order - BigUint::one();
    let r = loop {
        let bytes: [u8; 32] = rng.gen();
        let candidate = BigUint::from_bytes_be(&bytes);
        if candidate > BigUint::one() && candidate < max {
            break candidate;
        }
    };
    encrypt_scalar_with_r(plaintext, generator, public_key, &r, curve_order)
}

pub fn encrypt_scalar_with_r(
    plaintext: i64,
    generator: &E2Point,
    public_key: &E2Point,
    r: &BigUint,
    curve_order: &BigUint,
) -> Ciphertext {
    let m = BigUint::from(plaintext.unsigned_abs());
    let m_signed = if plaintext < 0 {
        curve_order - m
    } else {
        m
    };
    let c1 = generator.scalar_mul(r);
    let m_g = generator.scalar_mul(&m_signed);
    let r_pk = public_key.scalar_mul(r);
    let c2 = m_g.add(&r_pk);
    Ciphertext { c1, c2 }
}

pub fn homomorphic_add(a: &Ciphertext, b: &Ciphertext) -> Ciphertext {
    Ciphertext {
        c1: a.c1.add(&b.c1),
        c2: a.c2.add(&b.c2),
    }
}

pub fn homomorphic_scalar_mul(k: i64, ct: &Ciphertext, curve_order: &BigUint) -> Ciphertext {
    let kb = BigUint::from(k.unsigned_abs());
    let k_signed = if k < 0 {
        curve_order - kb
    } else {
        kb
    };
    Ciphertext {
        c1: ct.c1.scalar_mul(&k_signed),
        c2: ct.c2.scalar_mul(&k_signed),
    }
}

pub fn decrypt_pair(
    private_scalar: &BigUint,
    c1: &E2Point,
    c2: &E2Point,
    generator: &E2Point,
    table: &BsgsTable,
) -> Result<i64, crate::bsgs::BsgsError> {
    let c1_p = c1.to_projective();
    let c2_p = c2.to_projective();
    let s = CurveE2::mul_projective(&c1_p, private_scalar);
    let output = CurveE2::add_projective(&c2_p, &CurveE2::neg_projective(&s));
    let sk_c1 = CurveE2::mul_projective(&c1_p, private_scalar);
    let output2 = CurveE2::add_projective(&sk_c1, &CurveE2::neg_projective(&c2_p));
    let beta = E2Point::from_projective(&output);
    let beta_neg = E2Point::from_projective(&output2);
    table.giant_step(generator, &beta, &beta_neg)
}

pub fn decrypt_tensor(
    keys: &KeyMaterial,
    c1_cells: &[E2Point],
    c2_cells: &[E2Point],
    table: &BsgsTable,
) -> Result<Vec<i64>, crate::bsgs::BsgsError> {
    assert_eq!(c1_cells.len(), c2_cells.len());
    let n = c1_cells.len();
    if n >= PARALLEL_THRESHOLD {
        let sk = keys.private_scalar.clone();
        let g = keys.generator.clone();
        c1_cells
            .par_iter()
            .zip(c2_cells.par_iter())
            .map(|(a, b)| decrypt_pair(&sk, a, b, &g, table))
            .collect()
    } else {
        let mut out = Vec::with_capacity(n);
        for (a, b) in c1_cells.iter().zip(c2_cells.iter()) {
            out.push(decrypt_pair(
                &keys.private_scalar,
                a,
                b,
                &keys.generator,
                table,
            )?);
        }
        Ok(out)
    }
}

pub fn encrypt_tensor<R: Rng>(
    plaintexts: &[i32],
    keys: &KeyMaterial,
    rng: &mut R,
) -> (Vec<E2Point>, Vec<E2Point>) {
    let n = plaintexts.len();
    if n >= PARALLEL_THRESHOLD {
        let order = keys.curve_order.clone();
        let g = keys.generator.clone();
        let pk = keys.public_key.clone();
        let cts: Vec<Ciphertext> = plaintexts
            .par_iter()
            .map(|&m| {
                let mut local = rand::thread_rng();
                encrypt_scalar(m as i64, &g, &pk, &order, &mut local)
            })
            .collect();
        let c1 = cts.iter().map(|c| c.c1.clone()).collect();
        let c2 = cts.iter().map(|c| c.c2.clone()).collect();
        (c1, c2)
    } else {
        let mut c1 = Vec::with_capacity(n);
        let mut c2 = Vec::with_capacity(n);
        for &m in plaintexts {
            let ct = encrypt_scalar(
                m as i64,
                &keys.generator,
                &keys.public_key,
                &keys.curve_order,
                rng,
            );
            c1.push(ct.c1);
            c2.push(ct.c2);
        }
        (c1, c2)
    }
}

#[allow(dead_code)]
pub fn fixed_point_scale() -> u32 {
    FIXED_POINT_BITS
}
