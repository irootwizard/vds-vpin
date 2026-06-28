//! E1 (CP-SNARK / Ristretto255 scalar field) and E2 (AHE Weierstrass) parameters.
//!
//! vPIN embeds AHE messages into the SNARK field via mod-q reduction.

use libspartan::scalar::Scalar;
use serde::{Deserialize, Serialize};

/// E2 curve parameters from `src/cnn_networks/Client.py::curveE2Info()`.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CurveE2Params {
    pub curve_base_field: String,
    pub a: String,
    pub b: String,
    pub generator_x: String,
    pub generator_y: String,
    pub curve_order: String,
}

impl CurveE2Params {
    pub fn vpin_default() -> Self {
        Self {
            curve_base_field:
                "7237005577332262213973186563042994240857116359379907606001950938285454250989"
                    .into(),
            a: "3491403595575449084947959021303599933011749826127899762162894550148391771037"
                .into(),
            b: "3633908682298454119909199192149978293706667958442512986315258451820769071958"
                .into(),
            generator_x:
                "4561981307020378385254256586024830594940985765081274686120783167106442831732"
                    .into(),
            generator_y:
                "684120277165286233470758410892647831027470652988879249692043589061244861334"
                    .into(),
            curve_order:
                "7237005577332262213973186563042994240704759454384003648147593987722918659549"
                    .into(),
        }
    }
}

/// Ristretto255 scalar field modulus (E1 / CP-SNARK side).
pub fn e1_field_modulus_hex() -> &'static str {
    "1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed"
}

/// **Canonical** u128 → scalar encoding (commitments, RLC, future L1).
pub fn embed_u128_to_scalar(value: u128) -> Scalar {
    let mut wide = [0u8; 64];
    wide[..16].copy_from_slice(&value.to_le_bytes());
    Scalar::from_bytes_wide(&wide)
}

/// 32-byte encoding used by `point_mult.rs` witness (`dalek::Scalar::from(u128)`).
pub fn witness_u128_scalar_bytes(value: u128) -> [u8; 32] {
    use curve25519_dalek::scalar::Scalar as DalekScalar;
    DalekScalar::from(value).to_bytes()
}

/// True when commitment and witness encodings yield identical 32-byte canonical scalars.
pub fn u128_encoding_matches_witness(value: u128) -> bool {
    embed_u128_to_scalar(value).to_bytes() == witness_u128_scalar_bytes(value)
}

/// Map a big integer string (E2 field element) into SNARK scalar via mod-q reduction.
pub fn embed_bigint_str_to_scalar(s: &str) -> Scalar {
    let n = num::BigUint::parse_bytes(s.as_bytes(), 10).unwrap_or_default();
    let bytes = n.to_bytes_le();
    let mut wide = [0u8; 64];
    let copy_len = bytes.len().min(64);
    wide[..copy_len].copy_from_slice(&bytes[..copy_len]);
    Scalar::from_bytes_wide(&wide)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embed_matches_witness_small_values() {
        for v in [0u128, 1, 2, 255, 256, 65535, 1 << 32, (1u128 << 64) - 1] {
            assert!(
                u128_encoding_matches_witness(v),
                "encoding mismatch at v={}",
                v
            );
        }
    }

    #[test]
    fn embed_u128_is_deterministic() {
        let w = 46168577652891511897978894079897178031u128;
        assert_eq!(
            embed_u128_to_scalar(w).to_bytes(),
            embed_u128_to_scalar(w).to_bytes()
        );
    }
}
