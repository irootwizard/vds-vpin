//! E2 elliptic-curve stack (primefield + primeorder), independent of arkworks.

mod arithmetic;
mod bsgs;
mod codec;
mod curve;
mod field;
mod mul;
mod params;
mod point;
mod scalar;

pub use arithmetic::{AffinePoint, ProjectivePoint};
pub use bsgs::{BsgsError, BsgsTable, SharedBsgsTable, BSGS_M, IDENTITY_KEY};
pub use codec::{
    decrypt_pair, encrypt_scalar_with_r, EcCiphertext, EcDecryptProfile, EcEncryptProfile,
    EcKeyMaterial,
};
pub use curve::E2;
pub use field::FieldElement;
pub use params::{field_modulus, scalar_order};
pub use point::{
    be32_to_coord, coord_to_be32, ec_point_from_coords_be, scalar_mul_i64, warm_caches,
    wire_generator, EcE2Point,
};
pub use scalar::Scalar;
