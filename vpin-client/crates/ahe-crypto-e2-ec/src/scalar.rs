//! Scalar field Fr for E2 (Montgomery U256).

use crate::curve::E2;
use crate::params::ORDER_HEX;
use elliptic_curve::bigint::{Odd, U256};
use elliptic_curve::ff::PrimeField;
use elliptic_curve::scalar::{FromUintUnchecked, IsHigh};
use subtle::{Choice, ConstantTimeEq, CtOption};

const ORDER: Odd<U256> = Odd::<U256>::from_be_hex(ORDER_HEX);

primefield::monty_field_params! {
    name: ScalarParams,
    modulus: ORDER_HEX,
    uint: U256,
    byte_order: primefield::ByteOrder::BigEndian,
    multiplicative_generator: 2,
    doc: "Montgomery parameters for the E2 scalar field modulus n."
}

primefield::monty_field_element! {
    name: Scalar,
    params: ScalarParams,
    uint: U256,
    doc: "Element in the E2 scalar field modulo n."
}

primefield::monty_field_arithmetic! {
    name: Scalar,
    params: ScalarParams,
    uint: U256
}

primefield::monty_field_reduce! {
    name: Scalar,
    params: ScalarParams,
    uint: U256,
}

elliptic_curve::scalar_impls!(E2, Scalar);

impl AsRef<Scalar> for Scalar {
    fn as_ref(&self) -> &Scalar {
        self
    }
}

impl FromUintUnchecked for Scalar {
    type Uint = U256;

    fn from_uint_unchecked(uint: Self::Uint) -> Self {
        Self::from_uint_unchecked(uint)
    }
}

impl IsHigh for Scalar {
    fn is_high(&self) -> Choice {
        const MODULUS_SHR1: U256 = ORDER.as_ref().shr_vartime(1);
        use elliptic_curve::ctutils::CtGt;
        self.to_canonical().ct_gt(&MODULUS_SHR1).into()
    }
}

#[cfg(test)]
mod tests {
    use super::{Scalar, U256};

    primefield::test_primefield!(Scalar, U256);
}
