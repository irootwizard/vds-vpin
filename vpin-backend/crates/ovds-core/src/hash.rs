//! Hash functions for VADS protocol (Schnorr variant).
//!
//! HG:   {0,1}* → Z_q   (hash to scalar, for Schnorr challenge)
//! HPrime: tag → prime  (hash to 128-bit prime for RSA accumulator)
//! H2:   {0,1}* → [0, 2^128)  (hash to integer)

use num_bigint::BigUint;
use num_traits::Zero;
use sha2::{Digest, Sha256};

/// HG: Hash to a 256-bit integer (used as challenge scalar).
pub fn hg(data: &[u8]) -> BigUint {
    BigUint::from_bytes_be(&Sha256::digest(data))
}

/// HG indexed by (i, tag): HG(i || tag) → BigUint.
pub fn hg_indexed(i: u64, tag: &BigUint) -> BigUint {
    let mut data = i.to_be_bytes().to_vec();
    data.extend_from_slice(&tag.to_bytes_be());
    hg(&data)
}

/// HPrime: Hash a tag to a 128-bit prime number.
pub fn hprime(tag: &BigUint) -> BigUint {
    hash_to_prime(&tag.to_bytes_be(), 128)
}

/// H2: Hash to integer in [0, 2^λ).
pub fn h2(data: &[u8]) -> BigUint {
    let hash = Sha256::digest(data);
    BigUint::from_bytes_be(&hash[..16])
}

/// Hash arbitrary data to a prime of bit_length bits.
fn hash_to_prime(data: &[u8], bit_length: usize) -> BigUint {
    let byte_len = (bit_length + 7) / 8;
    let mut counter = 0u64;

    loop {
        let mut hasher = Sha256::new();
        hasher.update(data);
        hasher.update(counter.to_be_bytes());
        let hash = hasher.finalize();

        let mut bytes = vec![0u8; byte_len];
        let copy_len = byte_len.min(hash.len());
        bytes[..copy_len].copy_from_slice(&hash[..copy_len]);
        bytes[0] |= 0x80;
        bytes[byte_len - 1] |= 1;

        let candidate = BigUint::from_bytes_be(&bytes);
        if is_prime(&candidate) {
            return candidate;
        }
        counter += 1;
    }
}

fn is_prime(n: &BigUint) -> bool {
    if *n <= BigUint::from(2u32) {
        return *n == BigUint::from(2u32);
    }
    if n % 2u32 == Zero::zero() {
        return false;
    }

    let one = BigUint::from(1u32);
    let two = BigUint::from(2u32);
    let n_minus_1 = n - &one;
    let mut d = n_minus_1.clone();
    let mut s = 0u32;
    while &d % 2u32 == Zero::zero() {
        d >>= 1;
        s += 1;
    }

    let bases = [2u32, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37];
    for base in bases {
        let a = BigUint::from(base);
        if a >= *n { continue; }
        let mut x = a.modpow(&d, n);
        if x == one || x == n_minus_1 { continue; }
        let mut composite = true;
        for _ in 0..s - 1 {
            x = x.modpow(&two, n);
            if x == n_minus_1 { composite = false; break; }
        }
        if composite { return false; }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hprime_returns_primes() {
        let p1 = hprime(&BigUint::from(1u32));
        let p2 = hprime(&BigUint::from(2u32));
        assert_ne!(p1, p2);
        assert!(is_prime(&p1));
        assert!(is_prime(&p2));
    }

    #[test]
    fn h2_deterministic() {
        assert_eq!(h2(b"hello"), h2(b"hello"));
    }

    #[test]
    fn hg_deterministic() {
        let a = hg(b"test");
        let b = hg(b"test");
        assert_eq!(a, b);
        assert_ne!(hg(b"a"), hg(b"b"));
    }
}
