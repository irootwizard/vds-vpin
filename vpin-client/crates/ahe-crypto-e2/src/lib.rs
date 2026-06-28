//! E2 elliptic curve — custom short Weierstrass over Fp (arkworks).

mod curve;
mod point;

pub use curve::{CurveE2, E2Affine, E2Projective, Fr, Fq};
pub use point::{coord_to_be32, be32_to_coord, E2Point, KeyMaterial};
