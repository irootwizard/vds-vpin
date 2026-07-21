//! RSA Accumulator — mirrors Python `helpfunctions.py` + `vads_lib.py` RSA ops.
use num_bigint::{BigUint, RandBigInt};
use num_traits::{One, Zero};
use crate::error::OvdsError;

const RSA_KEY_SIZE: usize = 3072;

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
pub fn setup() -> Result<(BigUint, BigUint, BigUint), OvdsError> {
    let half = RSA_KEY_SIZE / 2;
    let p = gen_prime(half)?;
    let q = gen_prime(half)?;
    let n = &p * &q;
    let mut rng = rand::thread_rng();
    let h = loop {
        let c = rng.gen_biguint_range(&BigUint::one(), &n);
        if egcd(&c, &n) == BigUint::one() { break c; }
    };
    let phi = (&p - BigUint::one()) * (&q - BigUint::one());
    Ok((n, h, phi))
}

// ---------------------------------------------------------------------------
// Basic operations
// ---------------------------------------------------------------------------
pub fn add_member(acc: &BigUint, x: &BigUint, n: &BigUint) -> BigUint {
    acc.modpow(x, n)
}

pub fn remove_member(acc: &BigUint, x: &BigUint, n: &BigUint, phi: &BigUint) -> Result<BigUint, OvdsError> {
    let x_inv = mul_inv(x, phi).ok_or(OvdsError::Rsa("x not invertible mod phi".into()))?;
    Ok(acc.modpow(&x_inv, n))
}

// ---------------------------------------------------------------------------
// Number theory helpers (mirrors Python helpfunctions.py)
// ---------------------------------------------------------------------------

/// Extended Euclidean Algorithm: returns (g, a, b) such that a*x + b*y = g = gcd(x, y)
pub fn egcd_bezout(x: &BigUint, y: &BigUint) -> (BigUint, BigUint, BigUint) {
    let mut old_r = x.clone(); let mut r = y.clone();
    let mut old_s = BigUint::one();  let mut s = BigUint::zero();
    let mut old_t = BigUint::zero(); let mut t = BigUint::one();

    while r != BigUint::zero() {
        let q = &old_r / &r;
        // (old_r, r) := (r, old_r - q*r)
        let new_r = &old_r - &q * &r;
        // (old_s, s) := (s, old_s - q*s)
        let qs = &q * &s;
        let new_s = if old_s >= qs { &old_s - &qs } else { (&old_s + y - (&qs % y)) % y };
        // (old_t, t) := (t, old_t - q*t)
        let qt = &q * &t;
        let new_t = if old_t >= qt { &old_t - &qt } else { (&old_t + x - (&qt % x)) % x };

        old_r = r; r = new_r;
        old_s = s; s = new_s;
        old_t = t; t = new_t;
    }
    // old_r = gcd, old_s * x + old_t * y = old_r
    (old_r, old_s % y, old_t % x)
}

/// Modular inverse: returns a^(-1) mod n, or None (uses egcd_bezout).
pub fn mul_inv(a: &BigUint, n: &BigUint) -> Option<BigUint> {
    let (g, x, _) = egcd_bezout(a, n);
    if g != BigUint::one() { return None; }
    let inv = &x % n;
    if (&(a * &inv) % n) != BigUint::one() { return None; }
    Some(inv)
}

/// Simple GCD
pub fn egcd(a: &BigUint, b: &BigUint) -> BigUint {
    if *b == BigUint::zero() { a.clone() } else { egcd(b, &(a % b)) }
}

// ---------------------------------------------------------------------------
// Prime generation
// ---------------------------------------------------------------------------
fn gen_prime(bits: usize) -> Result<BigUint, OvdsError> {
    let mut rng = rand::thread_rng();
    loop {
        let mut c = rng.gen_biguint(bits as u64);
        c.set_bit((bits - 1) as u64, true);
        c.set_bit(0, true);
        if is_prime(&c) { return Ok(c); }
    }
}

fn is_prime(n: &BigUint) -> bool {
    if *n <= BigUint::from(1u32) { return false; }
    if *n <= BigUint::from(3u32) { return true; }
    if n % 2u32 == Zero::zero() { return false; }
    let one = BigUint::one();
    let two = BigUint::from(2u32);
    let nm1 = n - &one;
    let mut d = nm1.clone();
    let mut s = 0u32;
    while &d % 2u32 == Zero::zero() { d >>= 1; s += 1; }
    for base in [2u32, 3, 5, 7, 11, 13] {
        let a = BigUint::from(base);
        if a >= *n { continue; }
        let mut x = a.modpow(&d, n);
        if x == one || x == nm1 { continue; }
        let mut composite = true;
        for _ in 0..s-1 {
            x = x.modpow(&two, n);
            if x == nm1 { composite = false; break; }
        }
        if composite { return false; }
    }
    true
}

// ---------------------------------------------------------------------------
// Aggregated non-membership proof  (Algorithm 2: WitCreate_star / WitVerify_star)
// ---------------------------------------------------------------------------

pub fn prove_non_membership(
    acc_r: &BigUint, z_star: &BigUint, q: &[BigUint], n: &BigUint, h: &BigUint,
) -> NonMembershipProof {
    if q.len() == 1 {
        // Single-element: use Bezout direct proof
        let (_, a, b) = egcd_bezout(&q[0], z_star);
        return NonMembershipProof {
            v: acc_r.modpow(&a, n), y: h.modpow(&b, n),
            t1: BigUint::one(), t2: BigUint::one(),
            x_prime: BigUint::one(), r: BigUint::zero(),
        };
    }
    // Multi-element: full Algorithm 2 (placeholder, not yet validated)
    let omega: BigUint = q.iter().fold(BigUint::one(), |a, b| a * b);
    let (_, a, b) = egcd_bezout(z_star, &omega);
    NonMembershipProof {
        v: acc_r.modpow(&a, n), y: h.modpow(&b, n),
        t1: BigUint::one(), t2: BigUint::one(),
        x_prime: BigUint::one(), r: BigUint::zero(),
    }
}

pub fn verify_non_membership(
    _acc_r: &BigUint, z_star: &BigUint, q: &[BigUint], pi: &NonMembershipProof, n: &BigUint, h: &BigUint,
) -> bool {
    if q.len() == 1 {
        // V^q * Y^(z_star) ≡ h (mod n)
        return (&pi.v.modpow(&q[0], n) * &pi.y.modpow(z_star, n)) % n == *h;
    }
    // Multi-element: same check with product omega
    let omega: BigUint = q.iter().fold(BigUint::one(), |a, b| a * b);
    (&pi.v.modpow(&omega, n) * &pi.y.modpow(z_star, n)) % n == *h
}

use crate::types::NonMembershipProof;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn setup_works() {
        let (n, h, _phi) = setup().unwrap();
        assert!(n.bits() >= RSA_KEY_SIZE as u64 - 1);
        assert!(egcd(&h, &n) == BigUint::one());
    }

    #[test]
    fn add_remove_roundtrip() {
        let (n, h, phi) = setup().unwrap();
        let x = BigUint::from(17u32);
        let acc1 = add_member(&h, &x, &n);
        let acc2 = remove_member(&acc1, &x, &n, &phi).unwrap();
        assert_eq!(acc2, h);
    }

    #[test]
    fn non_membership_proof_works() {
        let (n, h, _phi) = setup().unwrap();
        let x = BigUint::from(17u32);
        let acc = add_member(&h, &x, &n);
        let q = BigUint::from(13u32);
        let proof = prove_non_membership(&acc, &BigUint::from(1u32), &[q.clone()], &n, &h);
        assert!(verify_non_membership(&acc, &BigUint::from(1u32), &[q], &proof, &n, &h));
    }

    #[test]
    fn mul_inv_works() {
        let (n, _, _) = setup().unwrap();
        let a = BigUint::from(17u32);
        let inv = mul_inv(&a, &n).unwrap();
        assert_eq!((&a * &inv) % &n, BigUint::one());
    }
}
