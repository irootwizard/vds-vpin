//! Wire-format points and projective group helpers.
//!
//! Wire decode follows ark `from_coords_be` idea (direct field bytes); projective cache
//! avoids re-decode in encrypt→decrypt loops (reference: k256 keeps projective in hot paths).

use std::sync::{Arc, OnceLock};

use num_bigint::BigUint;
use num_traits::Zero;

use crate::arithmetic::{AffinePoint, ProjectivePoint, BASEPOINT_WINDOW, E2_BASEPOINT_TABLE};
use crate::curve::E2;
use crate::mul::{mul_projective_vartime, CachedWnafBase, CachedWnafScalar};
use crate::scalar::Scalar;
use elliptic_curve::BatchNormalize;
use elliptic_curve::ops::Reduce;
use elliptic_curve::point::AffineCoordinates;
use elliptic_curve::FieldBytes;
use primeorder::BasepointTable;

#[derive(Debug)]
struct PointCache {
    x: [u8; 32],
    y: [u8; 32],
    proj: OnceLock<ProjectivePoint>,
    wnaf: OnceLock<CachedWnafBase>,
}

/// On-wire point: BE u256 coordinates; identity is (0, 0).
#[derive(Clone, Debug)]
pub enum EcE2Point {
    Identity,
    Affine {
        x: [u8; 32],
        y: [u8; 32],
        #[allow(dead_code)]
        cache: Arc<PointCache>,
    },
}

impl PartialEq for EcE2Point {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (EcE2Point::Identity, EcE2Point::Identity) => true,
            (
                EcE2Point::Affine { x: x1, y: y1, .. },
                EcE2Point::Affine { x: x2, y: y2, .. },
            ) => x1 == x2 && y1 == y2,
            _ => false,
        }
    }
}

impl Eq for EcE2Point {}

impl EcE2Point {
    pub fn from_projective(p: &ProjectivePoint) -> Self {
        let (x, y) = lookup_key_projective(p);
        if x == [0u8; 32] && y == [0u8; 32] {
            return EcE2Point::Identity;
        }
        let cache = Arc::new(PointCache {
            x,
            y,
            proj: OnceLock::new(),
            wnaf: OnceLock::new(),
        });
        let _ = cache.proj.set(*p);
        let _ = cache.wnaf.set(CachedWnafBase::new(*p));
        EcE2Point::Affine { x, y, cache }
    }

    /// Batch-normalize two projective points → wire pair (one inversion batch).
    pub fn from_projective_pair(a: &ProjectivePoint, b: &ProjectivePoint) -> (Self, Self) {
        let affines =
            <ProjectivePoint as BatchNormalize<[ProjectivePoint; 2]>>::batch_normalize(&[*a, *b]);
        (
            Self::from_projective_with_affine(a, &affines[0]),
            Self::from_projective_with_affine(b, &affines[1]),
        )
    }

    fn from_projective_with_affine(p: &ProjectivePoint, a: &AffinePoint) -> Self {
        if bool::from(a.is_identity()) {
            return EcE2Point::Identity;
        }
        let x: [u8; 32] = a.x().into();
        let y: [u8; 32] = a.y().into();
        let cache = Arc::new(PointCache {
            x,
            y,
            proj: OnceLock::new(),
            wnaf: OnceLock::new(),
        });
        let _ = cache.proj.set(*p);
        let _ = cache.wnaf.set(CachedWnafBase::new(*p));
        EcE2Point::Affine { x, y, cache }
    }

    pub fn to_projective(&self) -> ProjectivePoint {
        match self {
            EcE2Point::Identity => ProjectivePoint::IDENTITY,
            EcE2Point::Affine { x, y, cache } => *cache.proj.get_or_init(|| coords_to_projective(x, y)),
        }
    }

    pub fn add(&self, other: &EcE2Point) -> EcE2Point {
        EcE2Point::from_projective(&add_projective(
            &self.to_projective(),
            &other.to_projective(),
        ))
    }

    pub fn neg(&self) -> EcE2Point {
        EcE2Point::from_projective(&neg_projective(&self.to_projective()))
    }

    pub fn scalar_mul(&self, k: &BigUint) -> EcE2Point {
        EcE2Point::from_projective(&mul_projective(&self.to_projective(), k))
    }

    pub fn scalar_mul_i64(&self, k: i64) -> EcE2Point {
        EcE2Point::from_projective(&scalar_mul_i64(&self.to_projective(), k))
    }

    pub fn lookup_key(&self) -> ([u8; 32], [u8; 32]) {
        match self {
            EcE2Point::Identity => ([0u8; 32], [0u8; 32]),
            EcE2Point::Affine { x, y, .. } => (*x, *y),
        }
    }
}

pub fn wire_generator() -> EcE2Point {
    EcE2Point::from_projective(&ProjectivePoint::GENERATOR)
}

pub fn add_projective(a: &ProjectivePoint, b: &ProjectivePoint) -> ProjectivePoint {
    a.add(b)
}

pub fn neg_projective(p: &ProjectivePoint) -> ProjectivePoint {
    p.neg()
}

pub fn mul_projective(p: &ProjectivePoint, k: &BigUint) -> ProjectivePoint {
    if k.is_zero() {
        return ProjectivePoint::IDENTITY;
    }
    let s = scalar_from_biguint(k);
    if bool::from(s.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    mul_projective_vartime(p, &s)
}

pub fn mul_projective_scalar(p: &ProjectivePoint, k: &Scalar) -> ProjectivePoint {
    if bool::from(k.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    mul_projective_vartime(p, k)
}

pub fn mul_projective_scalar_cached(
    p: &ProjectivePoint,
    wnaf: Option<&CachedWnafBase>,
    k: &Scalar,
) -> ProjectivePoint {
    if bool::from(k.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    if let Some(c) = wnaf {
        return c.mul(k);
    }
    mul_projective_vartime(p, k)
}

pub fn mul_projective_digits_cached(
    wnaf: Option<&CachedWnafBase>,
    digits: &crate::mul::CachedWnafDigits,
    fallback_p: &ProjectivePoint,
    fallback_k: &Scalar,
) -> ProjectivePoint {
    if let Some(c) = wnaf {
        return c.mul_digits(digits);
    }
    mul_projective_vartime(fallback_p, fallback_k)
}

pub fn cached_wnaf_from_point(p: &EcE2Point) -> Option<&CachedWnafBase> {
    match p {
        EcE2Point::Identity => None,
        EcE2Point::Affine { cache, .. } => cache.wnaf.get(),
    }
}

pub fn mul_generator(k: &BigUint) -> ProjectivePoint {
    if k.is_zero() {
        return ProjectivePoint::IDENTITY;
    }
    let s = scalar_from_biguint(k);
    if bool::from(s.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    basepoint_table().mul_vartime(&s)
}

pub fn mul_generator_scalar(k: &Scalar) -> ProjectivePoint {
    if bool::from(k.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    basepoint_table().mul_vartime(k)
}

pub fn lookup_key_affine(a: &AffinePoint) -> ([u8; 32], [u8; 32]) {
    if bool::from(a.is_identity()) {
        return ([0u8; 32], [0u8; 32]);
    }
    (a.x().into(), a.y().into())
}

pub fn lookup_key_projective(p: &ProjectivePoint) -> ([u8; 32], [u8; 32]) {
    lookup_key_affine(&p.to_affine())
}

pub fn lookup_keys_projective_batch(points: &[ProjectivePoint]) -> Vec<([u8; 32], [u8; 32])> {
    match points.len() {
        0 => vec![],
        1 => vec![lookup_key_projective(&points[0])],
        2 => {
            let affines =
                <ProjectivePoint as BatchNormalize<[ProjectivePoint; 2]>>::batch_normalize(&[
                    points[0], points[1],
                ]);
            affines.iter().map(lookup_key_affine).collect()
        }
        _ => points.iter().map(lookup_key_projective).collect(),
    }
}

pub fn add_projective_mixed(p: &ProjectivePoint, q: &AffinePoint) -> ProjectivePoint {
    p + q
}

pub fn scalar_from_biguint(n: &BigUint) -> Scalar {
    if n.bits() <= 64 {
        if let Some(u) = n.to_u64_digits().first().copied() {
            return Scalar::from(u);
        }
    }
    let bytes = n.to_bytes_be();
    let mut buf = [0u8; 32];
    let start = 32usize.saturating_sub(bytes.len());
    buf[start..].copy_from_slice(&bytes);
    let fb = FieldBytes::<E2>::from(buf);
    Scalar::reduce(&fb)
}

pub fn scalar_mul_i64(p: &ProjectivePoint, k: i64) -> ProjectivePoint {
    if k == 0 {
        return ProjectivePoint::IDENTITY;
    }
    let s = scalar_from_i64(k);
    if bool::from(s.is_zero()) {
        return ProjectivePoint::IDENTITY;
    }
    mul_projective_vartime(p, &s)
}

pub fn scalar_from_i64(k: i64) -> Scalar {
    if k == 0 {
        return Scalar::ZERO;
    }
    let abs = BigUint::from(k.unsigned_abs());
    let order = crate::params::scalar_order();
    let n = if k < 0 { order - abs } else { abs };
    scalar_from_biguint(&n)
}

pub fn be32_to_coord(bytes: &[u8; 32]) -> BigUint {
    BigUint::from_bytes_be(bytes)
}

pub fn coord_to_be32(n: &BigUint) -> [u8; 32] {
    let bytes = n.to_bytes_be();
    let mut out = [0u8; 32];
    let start = 32usize.saturating_sub(bytes.len());
    out[start..].copy_from_slice(&bytes);
    out
}

pub fn warm_caches() {
    let _ = basepoint_table();
    let _ = mul_generator(&BigUint::from(1u32));
}

fn basepoint_table() -> &'static BasepointTable<ProjectivePoint, BASEPOINT_WINDOW> {
    &E2_BASEPOINT_TABLE
}

/// BE wire coordinates → projective (ark `from_coords_be` style via `from_coordinates`).
fn coords_to_projective(x: &[u8; 32], y: &[u8; 32]) -> ProjectivePoint {
    coords_to_projective_checked(x, y).unwrap_or(ProjectivePoint::IDENTITY)
}

/// Trusted wire import: same as cold decode, exposed for external points.
pub fn coords_to_projective_checked(x: &[u8; 32], y: &[u8; 32]) -> Option<ProjectivePoint> {
    if *x == [0u8; 32] && *y == [0u8; 32] {
        return Some(ProjectivePoint::IDENTITY);
    }
    let x_fb = FieldBytes::<E2>::from(*x);
    let y_fb = FieldBytes::<E2>::from(*y);
    let ct = AffinePoint::from_coordinates(&x_fb, &y_fb);
    if bool::from(ct.is_some()) {
        Some(ProjectivePoint::from(ct.unwrap()))
    } else {
        None
    }
}

pub fn ec_point_from_coords_be(x: [u8; 32], y: [u8; 32]) -> EcE2Point {
    match coords_to_projective_checked(&x, &y) {
        Some(p) => EcE2Point::from_projective(&p),
        None if x == [0u8; 32] && y == [0u8; 32] => EcE2Point::Identity,
        None => EcE2Point::Identity,
    }
}
