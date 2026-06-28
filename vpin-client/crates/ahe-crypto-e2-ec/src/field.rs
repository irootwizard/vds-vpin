//! Base field Fq for E2 (Montgomery U256).

use crate::params::MODULUS_HEX;
use elliptic_curve::bigint::U256;
use elliptic_curve::ff::PrimeField;
use elliptic_curve::ops::BatchInvert;
use subtle::{Choice, ConstantTimeEq, CtOption};

primefield::monty_field_params! {
    name: FieldParams,
    modulus: MODULUS_HEX,
    uint: U256,
    byte_order: primefield::ByteOrder::BigEndian,
    multiplicative_generator: 2,
    doc: "Montgomery parameters for the E2 base field modulus p."
}

primefield::monty_field_element! {
    name: FieldElement,
    params: FieldParams,
    uint: U256,
    doc: "Element in the E2 base field modulo p."
}

primefield::monty_field_arithmetic! {
    name: FieldElement,
    params: FieldParams,
    uint: U256
}

impl BatchInvert for FieldElement {}

pub type FieldBytes = elliptic_curve::FieldBytes<crate::curve::E2>;

#[cfg(test)]
mod tests {
    use super::{FieldElement, U256};

    primefield::test_primefield!(FieldElement, U256);
}
