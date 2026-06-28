//! E2 curve constants (shared data only — no arkworks code).

use num_bigint::BigUint;

pub const MODULUS_HEX: &str =
    "1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed";
pub const ORDER_HEX: &str =
    "0fffffffffffffffffffffffffffffffa2401a7ec4cc55998805b0ecdfee85dd";
pub const COEFF_A_HEX: &str =
    "07b8107ce99376405e4db7db030f57cb3a4b2f100ff59f448e262a3f65321b9d";
pub const COEFF_B_HEX: &str =
    "0808b82c5aab70fa925dab6f89299504647e8fbf01ec7638f940ec6e44ca5356";
pub const GENERATOR_X_HEX: &str =
    "0a15fd6b3bb3ab70f565ba3ca5cd67722440507997356a93211ece9d7ceba774";
pub const GENERATOR_Y_HEX: &str =
    "018332c76612297fb38f905b850a7cc559018882a807fdbe1f8aaf3d6287bb96";

pub fn field_modulus() -> BigUint {
    BigUint::parse_bytes(
        b"7237005577332262213973186563042994240857116359379907606001950938285454250989",
        10,
    )
    .unwrap()
}

pub fn scalar_order() -> BigUint {
    BigUint::parse_bytes(
        b"7237005577332262213973186563042994240704759454384003648147593987722918659549",
        10,
    )
    .unwrap()
}
