use ark_ec::{short_weierstrass::SWCurveConfig, AffineRepr, CurveConfig, CurveGroup};
use ark_ff::{fields::*, BigInteger, MontFp, PrimeField};

#[derive(MontConfig)]
#[modulus = "7237005577332262213973186563042994240857116359379907606001950938285454250989"]
#[generator = "2"]
pub struct FqConfig;

pub type Fq = Fp<MontBackend<FqConfig, 4>, 4>;

#[derive(MontConfig)]
#[modulus = "7237005577332262213973186563042994240704759454384003648147593987722918659549"]
#[generator = "2"]
pub struct FrConfig;

pub type Fr = Fp<MontBackend<FrConfig, 4>, 4>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct E2Config;

impl CurveConfig for E2Config {
    type BaseField = Fq;
    type ScalarField = Fr;
    const COFACTOR: &'static [u64] = &[1];
    const COFACTOR_INV: Fr = MontFp!("1");
}

impl SWCurveConfig for E2Config {
    const COEFF_A: Fq = MontFp!(
        "3491403595575449084947959021303599933011749826127899762162894550148391771037"
    );
    const COEFF_B: Fq = MontFp!(
        "3633908682298454119909199192149978293706667958442512986315258451820769071958"
    );
    const GENERATOR: ark_ec::short_weierstrass::Affine<E2Config> =
        ark_ec::short_weierstrass::Affine::new_unchecked(
            MontFp!(
                "4561981307020378385254256586024830594940985765081274686120783167106442831732"
            ),
            MontFp!(
                "684120277165286233470758410892647831027470652988879249692043589061244861334"
            ),
        );
}

pub type E2Affine = ark_ec::short_weierstrass::Affine<E2Config>;
pub type E2Projective = ark_ec::short_weierstrass::Projective<E2Config>;

pub struct CurveE2;

impl CurveE2 {
    pub fn generator() -> E2Affine {
        E2Config::GENERATOR
    }

    pub fn identity() -> E2Projective {
        E2Projective::zero()
    }

    pub fn order() -> num_bigint::BigUint {
        num_bigint::BigUint::parse_bytes(
            b"7237005577332262213973186563042994240704759454384003648147593987722918659549",
            10,
        )
        .unwrap()
    }

    pub fn scalar_from_biguint(n: &num_bigint::BigUint) -> Fr {
        Fr::from_le_bytes_mod_order(&n.to_bytes_le())
    }

    pub fn mul_generator(scalar: &num_bigint::BigUint) -> E2Projective {
        let s = Self::scalar_from_biguint(scalar);
        E2Config::GENERATOR.into_group() * s
    }

    pub fn mul_point(p: &E2Affine, scalar: &num_bigint::BigUint) -> E2Projective {
        if p.is_zero() {
            return E2Projective::zero();
        }
        let s = Self::scalar_from_biguint(scalar);
        (*p).into_group() * s
    }

    pub fn affine_from_projective(p: &E2Projective) -> E2Affine {
        p.into_affine()
    }

    pub fn coord_x_be(p: &E2Affine) -> Option<[u8; 32]> {
        if p.is_zero() {
            return None;
        }
        let x = p.x().unwrap().into_bigint().to_bytes_be();
        Some(pad_be32(&x))
    }

    pub fn coord_y_be(p: &E2Affine) -> Option<[u8; 32]> {
        if p.is_zero() {
            return None;
        }
        let y = p.y().unwrap().into_bigint().to_bytes_be();
        Some(pad_be32(&y))
    }

    pub fn from_coords_be(x: &[u8; 32], y: &[u8; 32]) -> Option<E2Affine> {
        if *x == [0u8; 32] && *y == [0u8; 32] {
            return Some(E2Affine::zero());
        }
        let xf = Fq::from_be_bytes_mod_order(x);
        let yf = Fq::from_be_bytes_mod_order(y);
        let a = E2Affine::new_unchecked(xf, yf);
        if a.is_on_curve() {
            Some(a)
        } else {
            None
        }
    }

    pub fn neg_projective(p: &E2Projective) -> E2Projective {
        -(*p)
    }

    pub fn add_projective(a: &E2Projective, b: &E2Projective) -> E2Projective {
        a + b
    }

    pub fn mul_projective(p: &E2Projective, scalar: &num_bigint::BigUint) -> E2Projective {
        *p * Self::scalar_from_biguint(scalar)
    }

    /// BSGS lookup key: identity uses (0,0), otherwise BE coordinate pair.
    pub fn lookup_key(p: &E2Projective) -> ([u8; 32], [u8; 32]) {
        let a = Self::affine_from_projective(p);
        if a.is_zero() {
            return ([0u8; 32], [0u8; 32]);
        }
        (
            Self::coord_x_be(&a).unwrap(),
            Self::coord_y_be(&a).unwrap(),
        )
    }
}

fn pad_be32(bytes: &[u8]) -> [u8; 32] {
    let mut out = [0u8; 32];
    let start = 32usize.saturating_sub(bytes.len());
    out[start..].copy_from_slice(bytes);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generator_non_zero() {
        let p = CurveE2::mul_generator(&num_bigint::BigUint::from(1u32));
        assert!(!CurveE2::affine_from_projective(&p).is_zero());
    }

    #[test]
    fn identity_zero() {
        assert!(CurveE2::affine_from_projective(&CurveE2::identity()).is_zero());
    }
}
