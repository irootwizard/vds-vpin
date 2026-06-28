use std::collections::HashMap;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use num_bigint::BigUint;
use thiserror::Error;

use crate::arithmetic::{AffinePoint, ProjectivePoint};
use crate::point::{
    add_projective_mixed, lookup_key_affine, lookup_key_projective, lookup_keys_projective_batch,
    mul_projective, neg_projective, EcE2Point,
};

pub const BSGS_M: u32 = 3_200_000;
const MAGIC: &[u8; 4] = b"BSG1";
const COORD_BYTES: usize = 32;
pub const IDENTITY_KEY: ([u8; 32], [u8; 32]) = ([0u8; 32], [0u8; 32]);

#[derive(Error, Debug)]
pub enum BsgsError {
    #[error("invalid BSGS file: {0}")]
    Invalid(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
}

pub struct BsgsTable {
    map: HashMap<([u8; 32], [u8; 32]), u32>,
}

pub type SharedBsgsTable = Arc<BsgsTable>;

impl BsgsTable {
    pub fn load(path: &Path) -> Result<Self, BsgsError> {
        let file = File::open(path)?;
        let mmap = unsafe { memmap2::Mmap::map(&file)? };
        Self::parse(&mmap)
    }

    pub fn parse(data: &[u8]) -> Result<Self, BsgsError> {
        if data.len() < 16 {
            return Err(BsgsError::Invalid("too short".into()));
        }
        if &data[0..4] != MAGIC {
            return Err(BsgsError::Invalid("bad magic".into()));
        }
        let m = u32::from_le_bytes(data[4..8].try_into().unwrap());
        if m != BSGS_M {
            return Err(BsgsError::Invalid(format!("m={m} expected {BSGS_M}")));
        }
        let count = u64::from_le_bytes(data[8..16].try_into().unwrap()) as usize;
        let entry_size = COORD_BYTES * 2 + 4;
        let expected = 16 + count * entry_size;
        if data.len() < expected {
            return Err(BsgsError::Invalid("truncated entries".into()));
        }
        let mut map = HashMap::with_capacity(count);
        let mut off = 16usize;
        for _ in 0..count {
            let mut x = [0u8; 32];
            let mut y = [0u8; 32];
            x.copy_from_slice(&data[off..off + 32]);
            off += 32;
            y.copy_from_slice(&data[off..off + 32]);
            off += 32;
            let j = u32::from_le_bytes(data[off..off + 4].try_into().unwrap());
            off += 4;
            map.insert((x, y), j);
        }
        Ok(Self { map })
    }

    pub fn lookup(&self, p: &EcE2Point) -> Option<u32> {
        self.map.get(&p.lookup_key()).copied()
    }

    pub fn lookup_affine(&self, p: &AffinePoint) -> Option<u32> {
        self.map.get(&lookup_key_affine(p)).copied()
    }

    pub fn lookup_projective(&self, p: &ProjectivePoint) -> Option<u32> {
        let key = lookup_key_projective(p);
        self.map.get(&key).copied()
    }

    pub fn giant_step(
        &self,
        alpha: &EcE2Point,
        beta: &EcE2Point,
        beta_neg: &EcE2Point,
    ) -> Result<i64, BsgsError> {
        self.giant_step_projective(
            alpha,
            &beta.to_projective(),
            &beta_neg.to_projective(),
        )
    }

    pub fn giant_step_projective(
        &self,
        alpha: &EcE2Point,
        beta: &ProjectivePoint,
        beta_neg: &ProjectivePoint,
    ) -> Result<i64, BsgsError> {
        let alpha_p = alpha.to_projective();
        self.giant_step_projective_raw_from_alpha(&alpha_p, beta, beta_neg)
    }

    pub fn giant_step_projective_raw(
        &self,
        beta: &ProjectivePoint,
        beta_neg: &ProjectivePoint,
    ) -> Result<i64, BsgsError> {
        let alpha_p = crate::arithmetic::ProjectivePoint::GENERATOR;
        self.giant_step_projective_raw_from_alpha(&alpha_p, beta, beta_neg)
    }

    fn giant_step_projective_raw_from_alpha(
        &self,
        alpha_p: &ProjectivePoint,
        beta: &ProjectivePoint,
        beta_neg: &ProjectivePoint,
    ) -> Result<i64, BsgsError> {
        let m = BigUint::from(BSGS_M);
        let inv_alpha_m = neg_projective(&mul_projective(alpha_p, &m));
        let step = inv_alpha_m.to_affine();

        let mut gamma = *beta;
        let mut gamma2 = *beta_neg;
        for i in 0..BSGS_M {
            let keys = lookup_keys_projective_batch(&[gamma, gamma2]);
            if let Some(j) = self.map.get(&keys[0]).copied() {
                return Ok(i as i64 * BSGS_M as i64 + j as i64);
            }
            if let Some(j) = self.map.get(&keys[1]).copied() {
                return Ok(-(i as i64 * BSGS_M as i64 + j as i64));
            }
            gamma = add_projective_mixed(&gamma, &step);
            gamma2 = add_projective_mixed(&gamma2, &step);
        }
        Err(BsgsError::Invalid("discrete log not found".into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture_table() -> Option<PathBuf> {
        let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/table.bin");
        if p.is_file() {
            Some(p)
        } else {
            None
        }
    }

    #[test]
    fn load_fixture_if_present() {
        if let Some(p) = fixture_table() {
            let t = BsgsTable::load(&p).expect("load");
            assert!(t.map.contains_key(&IDENTITY_KEY));
        }
    }
}
