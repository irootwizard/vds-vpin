//! E2 curve type definition.

use crate::params::ORDER_HEX;
use elliptic_curve::bigint::{Odd, U256};
use elliptic_curve::consts::U32;

/// Custom E2 prime-order short Weierstrass curve.
#[derive(Copy, Clone, Debug, Default, Eq, PartialEq, PartialOrd, Ord)]
pub struct E2;

const ORDER: Odd<U256> = Odd::<U256>::from_be_hex(ORDER_HEX);

impl elliptic_curve::Curve for E2 {
    type FieldBytesSize = U32;
    type Uint = U256;
    const ORDER: Odd<U256> = ORDER;
}

impl elliptic_curve::PrimeCurve for E2 {}

impl elliptic_curve::point::PointCompression for E2 {
    const COMPRESS_POINTS: bool = false;
}
