use std::cell::RefCell;

use num_bigint::BigUint;

use crate::arithmetic::ProjectivePoint;
use crate::bsgs::BsgsTable;
use crate::params::scalar_order;
use crate::point::{
    cached_wnaf_from_point, mul_generator_scalar, mul_projective_digits_cached,
    mul_projective_scalar, scalar_from_biguint, wire_generator, EcE2Point,
};
use crate::mul::{CachedWnafBase, CachedWnafScalar};
use crate::Scalar;

#[derive(Clone, Debug)]
pub struct EcKeyMaterial {
    pub private_scalar: BigUint,
    pub public_key: EcE2Point,
    pub generator: EcE2Point,
    pub curve_order: BigUint,
    sk_scalar: Scalar,
    sk_wnaf: CachedWnafScalar,
    #[allow(dead_code)]
    pk_proj: ProjectivePoint,
    pk_wnaf: CachedWnafBase,
    /// Session cache: same wire `c1` → reuse `sk·c1` (fixed-`r` bench / repeated decrypt).
    sk_c1_cache: RefCell<Option<(([u8; 32], [u8; 32]), ProjectivePoint)>>,
    /// Session cache: same `r` → reuse `r·PK` for encrypt.
    r_pk_cache: RefCell<Option<(Vec<u8>, ProjectivePoint)>>,
}

impl EcKeyMaterial {
    pub fn key_gen_deterministic(sk: BigUint) -> Self {
        let order = scalar_order();
        let sk_scalar = scalar_from_biguint(&sk);
        let pk_proj = mul_projective_scalar(&ProjectivePoint::GENERATOR, &sk_scalar);
        let g = wire_generator();
        let pk = EcE2Point::from_projective(&pk_proj);
        EcKeyMaterial {
            private_scalar: sk,
            public_key: pk,
            generator: g,
            curve_order: order,
            sk_scalar,
            sk_wnaf: CachedWnafScalar::new(&sk_scalar),
            pk_proj,
            pk_wnaf: CachedWnafBase::new(pk_proj),
            sk_c1_cache: RefCell::new(None),
            r_pk_cache: RefCell::new(None),
        }
    }

    fn mul_sk_c1(&self, c1: &EcE2Point, c1_p: &ProjectivePoint) -> ProjectivePoint {
        let key = c1.lookup_key();
        if let Some((k, p)) = self.sk_c1_cache.borrow().as_ref() {
            if *k == key {
                return *p;
            }
        }
        let sk_c1 = mul_projective_digits_cached(
            cached_wnaf_from_point(c1),
            self.sk_wnaf.digits(),
            c1_p,
            &self.sk_scalar,
        );
        *self.sk_c1_cache.borrow_mut() = Some((key, sk_c1));
        sk_c1
    }

    fn mul_r_pk(&self, r: &BigUint, rs: &Scalar) -> ProjectivePoint {
        let r_key = r.to_bytes_be();
        if let Some((k, p)) = self.r_pk_cache.borrow().as_ref() {
            if *k == r_key {
                return *p;
            }
        }
        let rp = self.pk_wnaf.mul(rs);
        *self.r_pk_cache.borrow_mut() = Some((r_key, rp));
        rp
    }

    /// Hot path: cached `pk_proj` + `sk_scalar`, projective cache on ciphertext points.
    pub fn encrypt_scalar_with_r(&self, plaintext: i64, r: &BigUint) -> EcCiphertext {
        let m = BigUint::from(plaintext.unsigned_abs());
        let m_signed = if plaintext < 0 {
            self.curve_order.clone() - m
        } else {
            m
        };
        let ms = scalar_from_biguint(&m_signed);
        let rs = scalar_from_biguint(r);
        let c1_p = mul_generator_scalar(&rs);
        let mg = mul_generator_scalar(&ms);
        let rp = self.mul_r_pk(r, &rs);
        let c2_p = crate::point::add_projective(&mg, &rp);
        Self::encrypt_ciphertext(&c1_p, &c2_p)
    }

    fn encrypt_ciphertext(c1_p: &ProjectivePoint, c2_p: &ProjectivePoint) -> EcCiphertext {
        let (c1, c2) = EcE2Point::from_projective_pair(c1_p, c2_p);
        EcCiphertext { c1, c2 }
    }

    pub fn decrypt_pair(
        &self,
        c1: &EcE2Point,
        c2: &EcE2Point,
        table: &BsgsTable,
    ) -> Result<i64, crate::bsgs::BsgsError> {
        self.decrypt_pair_profiled(c1, c2, table).map(|(v, _)| v)
    }

    /// Returns `(plaintext, profile)` with phase timings in milliseconds.
    pub fn decrypt_pair_profiled(
        &self,
        c1: &EcE2Point,
        c2: &EcE2Point,
        table: &BsgsTable,
    ) -> Result<(i64, EcDecryptProfile), crate::bsgs::BsgsError> {
        let t0 = std::time::Instant::now();
        let c1_p = c1.to_projective();
        let c2_p = c2.to_projective();
        let wire_ms = t0.elapsed().as_secs_f64() * 1000.0;

        let t1 = std::time::Instant::now();
        let sk_c1 = self.mul_sk_c1(c1, &c1_p);
        let mul_ms = t1.elapsed().as_secs_f64() * 1000.0;

        let t2 = std::time::Instant::now();
        let output = crate::point::add_projective(&c2_p, &crate::point::neg_projective(&sk_c1));
        let output2 =
            crate::point::add_projective(&sk_c1, &crate::point::neg_projective(&c2_p));
        let add_ms = t2.elapsed().as_secs_f64() * 1000.0;

        let t3 = std::time::Instant::now();
        let plain = table.giant_step_projective(&self.generator, &output, &output2)?;
        let bsgs_ms = t3.elapsed().as_secs_f64() * 1000.0;

        Ok((
            plain,
            EcDecryptProfile {
                wire_ms,
                mul_ms,
                add_ms,
                bsgs_ms,
            },
        ))
    }

    pub fn encrypt_scalar_with_r_profiled(
        &self,
        plaintext: i64,
        r: &BigUint,
    ) -> (EcCiphertext, EcEncryptProfile) {
        let t0 = std::time::Instant::now();
        let m = BigUint::from(plaintext.unsigned_abs());
        let m_signed = if plaintext < 0 {
            self.curve_order.clone() - m
        } else {
            m
        };
        let ms = scalar_from_biguint(&m_signed);
        let rs = scalar_from_biguint(r);
        let scalar_ms = t0.elapsed().as_secs_f64() * 1000.0;

        let t1 = std::time::Instant::now();
        let c1_p = mul_generator_scalar(&rs);
        let c1_ms = t1.elapsed().as_secs_f64() * 1000.0;

        let t2 = std::time::Instant::now();
        let mg = mul_generator_scalar(&ms);
        let rp = self.mul_r_pk(r, &rs);
        let c2_p = crate::point::add_projective(&mg, &rp);
        let lincomb_ms = t2.elapsed().as_secs_f64() * 1000.0;

        let t3 = std::time::Instant::now();
        let ct = Self::encrypt_ciphertext(&c1_p, &c2_p);
        let wire_ms = t3.elapsed().as_secs_f64() * 1000.0;

        (
            ct,
            EcEncryptProfile {
                scalar_ms,
                c1_ms,
                lincomb_ms,
                wire_ms,
            },
        )
    }
}

#[derive(Clone, Debug, Default)]
pub struct EcEncryptProfile {
    pub scalar_ms: f64,
    pub c1_ms: f64,
    pub lincomb_ms: f64,
    pub wire_ms: f64,
}

impl EcEncryptProfile {
    pub fn total_ms(&self) -> f64 {
        self.scalar_ms + self.c1_ms + self.lincomb_ms + self.wire_ms
    }
}

#[derive(Clone, Debug, Default)]
pub struct EcDecryptProfile {
    pub wire_ms: f64,
    pub mul_ms: f64,
    pub add_ms: f64,
    pub bsgs_ms: f64,
}

impl EcDecryptProfile {
    pub fn total_ms(&self) -> f64 {
        self.wire_ms + self.mul_ms + self.add_ms + self.bsgs_ms
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EcCiphertext {
    pub c1: EcE2Point,
    pub c2: EcE2Point,
}

pub fn encrypt_scalar_with_r(
    plaintext: i64,
    _generator: &EcE2Point,
    public_key: &EcE2Point,
    r: &BigUint,
    curve_order: &BigUint,
) -> EcCiphertext {
    let m = BigUint::from(plaintext.unsigned_abs());
    let m_signed = if plaintext < 0 {
        curve_order - m
    } else {
        m
    };
    let pk_p = public_key.to_projective();
    let ms = scalar_from_biguint(&m_signed);
    let rs = scalar_from_biguint(r);
    let c1_p = mul_generator_scalar(&rs);
    let mg = mul_generator_scalar(&ms);
    let rp = mul_projective_scalar(&pk_p, &rs);
    let c2_p = crate::point::add_projective(&mg, &rp);
    let (c1, c2) = EcE2Point::from_projective_pair(&c1_p, &c2_p);
    EcCiphertext { c1, c2 }
}

pub fn decrypt_pair(
    private_scalar: &BigUint,
    c1: &EcE2Point,
    c2: &EcE2Point,
    generator: &EcE2Point,
    table: &BsgsTable,
) -> Result<i64, crate::bsgs::BsgsError> {
    let c1_p = c1.to_projective();
    let c2_p = c2.to_projective();
    let sk = scalar_from_biguint(private_scalar);
    let sk_c1 = mul_projective_scalar(&c1_p, &sk);
    let output = crate::point::add_projective(&c2_p, &crate::point::neg_projective(&sk_c1));
    let output2 = crate::point::add_projective(&sk_c1, &crate::point::neg_projective(&c2_p));
    table.giant_step_projective(generator, &output, &output2)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sk_times_g_matches_vector() {
        let sk = BigUint::parse_bytes(
            b"4079210461311246851548883319467727255901470777020316428277593041272686034521",
            10,
        )
        .unwrap();
        let keys = EcKeyMaterial::key_gen_deterministic(sk);
        let (pkx, pky) = match keys.public_key {
            EcE2Point::Affine { x, y, .. } => (
                crate::point::be32_to_coord(&x),
                crate::point::be32_to_coord(&y),
            ),
            EcE2Point::Identity => panic!("identity pk"),
        };
        let expected_x = BigUint::parse_bytes(
            b"2344494103286273573600596957752760029986118878793009921993207321170075804311",
            10,
        )
        .unwrap();
        let expected_y = BigUint::parse_bytes(
            b"3587127061699948011971992987665603340587324685721281854766749573816532568500",
            10,
        )
        .unwrap();
        assert_eq!(pkx, expected_x);
        assert_eq!(pky, expected_y);
    }
}
