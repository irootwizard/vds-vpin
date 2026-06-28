use std::collections::HashMap;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use ahe_crypto_e2::{CurveE2, E2Point, E2Projective};
use memmap2::Mmap;
use num_bigint::BigUint;
use thiserror::Error;

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
        let mmap = unsafe { Mmap::map(&file)? };
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

    pub fn lookup(&self, p: &E2Point) -> Option<u32> {
        match p {
            E2Point::Identity => self.map.get(&IDENTITY_KEY).copied(),
            E2Point::Affine { x, y } => self.map.get(&(*x, *y)).copied(),
        }
    }

    pub fn lookup_projective(&self, p: &E2Projective) -> Option<u32> {
        let key = CurveE2::lookup_key(p);
        self.map.get(&key).copied()
    }

    pub fn giant_step(
        &self,
        alpha: &E2Point,
        beta: &E2Point,
        beta_neg: &E2Point,
    ) -> Result<i64, BsgsError> {
        let alpha_p = alpha.to_projective();
        let m = BigUint::from(BSGS_M);
        let inv_alpha_m = CurveE2::neg_projective(&CurveE2::mul_projective(&alpha_p, &m));

        let mut gamma = beta.to_projective();
        let mut gamma2 = beta_neg.to_projective();
        for i in 0..BSGS_M {
            if let Some(j) = self.lookup_projective(&gamma) {
                return Ok(i as i64 * BSGS_M as i64 + j as i64);
            }
            if let Some(j) = self.lookup_projective(&gamma2) {
                return Ok(-(i as i64 * BSGS_M as i64 + j as i64));
            }
            gamma = CurveE2::add_projective(&gamma, &inv_alpha_m);
            gamma2 = CurveE2::add_projective(&gamma2, &inv_alpha_m);
        }
        Err(BsgsError::Invalid("discrete log not found".into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture_table() -> Option<PathBuf> {
        let p = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/table.bin");
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
