//! Variable-base scalar multiplication (reference: k256 `mul.rs` + primeorder `LookupTable`).

use crate::arithmetic::ProjectivePoint;
use crate::scalar::Scalar;
use elliptic_curve::array::typenum::{U5, U257};
use std::sync::OnceLock;
use wnaf::{WnafBase, WnafScalar};

pub type WnafPoint = WnafBase<ProjectivePoint, U5>;
pub type CachedWnafDigits = WnafScalar<Scalar, U5, U257>;

/// `[k]P` in variable time using w-NAF (Straus), per `wnaf` crate / k256 pattern.
#[inline]
pub fn mul_projective_vartime(p: &ProjectivePoint, k: &Scalar) -> ProjectivePoint {
    let base = WnafPoint::new(*p);
    mul_with_wnaf_base(&base, k)
}

/// Reuse a precomputed w-NAF window table (same base, many scalars).
#[inline]
pub fn mul_with_wnaf_base(base: &WnafPoint, k: &Scalar) -> ProjectivePoint {
    let scalar = CachedWnafDigits::new(k);
    base * &scalar
}

#[inline]
pub fn mul_with_wnaf_pair(base: &WnafPoint, digits: &CachedWnafDigits) -> ProjectivePoint {
    base * digits
}

/// Precomputed w-NAF digits for a fixed scalar (k256 reuses `WnafScalar` across muls).
#[derive(Clone, Debug)]
pub struct CachedWnafScalar {
    digits: CachedWnafDigits,
}

impl CachedWnafScalar {
    pub fn new(k: &Scalar) -> Self {
        Self {
            digits: CachedWnafDigits::new(k),
        }
    }

    pub fn digits(&self) -> &CachedWnafDigits {
        &self.digits
    }
}

/// Lazy w-NAF table tied to a fixed base point.
#[derive(Debug)]
pub struct CachedWnafBase {
    point: ProjectivePoint,
    table: OnceLock<WnafPoint>,
}

impl Clone for CachedWnafBase {
    fn clone(&self) -> Self {
        Self::new(self.point)
    }
}

impl CachedWnafBase {
    pub fn new(point: ProjectivePoint) -> Self {
        Self {
            point,
            table: OnceLock::new(),
        }
    }

    fn table(&self) -> &WnafPoint {
        self.table
            .get_or_init(|| WnafPoint::new(self.point))
    }

    pub fn mul(&self, k: &Scalar) -> ProjectivePoint {
        mul_with_wnaf_base(self.table(), k)
    }

    pub fn mul_digits(&self, digits: &CachedWnafDigits) -> ProjectivePoint {
        mul_with_wnaf_pair(self.table(), digits)
    }
}
