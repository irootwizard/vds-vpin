use ark_ec::AffineRepr;
use num_bigint::BigUint;
use num_traits::{One, Zero};
use rand::Rng;

use crate::curve::{CurveE2, E2Projective};

/// Wire / homomorphic point: identity or affine coordinates (BE u256).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum E2Point {
    Identity,
    Affine { x: [u8; 32], y: [u8; 32] },
}

impl E2Point {
    pub fn from_projective(p: &E2Projective) -> Self {
        let a = CurveE2::affine_from_projective(p);
        if a.is_zero() {
            return E2Point::Identity;
        }
        E2Point::Affine {
            x: CurveE2::coord_x_be(&a).unwrap(),
            y: CurveE2::coord_y_be(&a).unwrap(),
        }
    }

    pub fn to_projective(&self) -> E2Projective {
        match self {
            E2Point::Identity => E2Projective::zero(),
            E2Point::Affine { x, y } => {
                CurveE2::from_coords_be(x, y)
                    .map(|a| a.into_group())
                    .unwrap_or_else(E2Projective::zero)
            }
        }
    }

    pub fn add(&self, other: &E2Point) -> E2Point {
        let out = self.to_projective() + other.to_projective();
        E2Point::from_projective(&out)
    }

    pub fn scalar_mul(&self, k: &BigUint) -> E2Point {
        if k.is_zero() || matches!(self, E2Point::Identity) {
            return E2Point::Identity;
        }
        let s = CurveE2::scalar_from_biguint(k);
        let out = self.to_projective() * s;
        E2Point::from_projective(&out)
    }

    /// Projective scalar multiply without intermediate affine round-trip.
    pub fn scalar_mul_projective(&self, k: &BigUint) -> E2Projective {
        if k.is_zero() || matches!(self, E2Point::Identity) {
            return E2Projective::zero();
        }
        let s = CurveE2::scalar_from_biguint(k);
        self.to_projective() * s
    }

    pub fn neg_projective(&self) -> E2Projective {
        -self.to_projective()
    }

    pub fn scalar_mul_i64(&self, k: i64) -> E2Point {
        if k == 0 {
            return E2Point::Identity;
        }
        if k < 0 {
            return self.scalar_mul(&BigUint::from((-k) as u64)).neg();
        }
        self.scalar_mul(&BigUint::from(k as u64))
    }

    pub fn neg(&self) -> E2Point {
        E2Point::from_projective(&(-self.to_projective()))
    }
}

pub fn coord_to_be32(n: &BigUint) -> [u8; 32] {
    let bytes = n.to_bytes_be();
    let mut out = [0u8; 32];
    let start = 32usize.saturating_sub(bytes.len());
    out[start..].copy_from_slice(&bytes);
    out
}

pub fn be32_to_coord(bytes: &[u8; 32]) -> BigUint {
    BigUint::from_bytes_be(bytes)
}

#[derive(Clone, Debug)]
pub struct KeyMaterial {
    pub private_scalar: BigUint,
    pub public_key: E2Point,
    pub generator: E2Point,
    pub curve_order: BigUint,
}

impl KeyMaterial {
    pub fn key_gen<R: Rng>(rng: &mut R) -> Self {
        let order = CurveE2::order();
        let max = &order - BigUint::one();
        let sk = loop {
            let bytes: [u8; 32] = rng.gen();
            let candidate = BigUint::from_bytes_be(&bytes);
            if candidate > BigUint::zero() && candidate < max {
                break candidate;
            }
        };
        let pk_proj = CurveE2::mul_generator(&sk);
        let g = E2Point::from_projective(&CurveE2::generator().into_group());
        KeyMaterial {
            private_scalar: sk,
            public_key: E2Point::from_projective(&pk_proj),
            generator: g,
            curve_order: order,
        }
    }

    pub fn key_gen_deterministic(sk: BigUint) -> Self {
        let order = CurveE2::order();
        let pk_proj = CurveE2::mul_generator(&sk);
        let g = E2Point::from_projective(&CurveE2::generator().into_group());
        KeyMaterial {
            private_scalar: sk,
            public_key: E2Point::from_projective(&pk_proj),
            generator: g,
            curve_order: order,
        }
    }
}
