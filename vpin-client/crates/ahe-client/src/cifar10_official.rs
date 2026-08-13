//! Official CIFAR-10 — Rust lane (binary batch files, same layout as Krizhevsky tar).

use std::path::{Path, PathBuf};

use thiserror::Error;

use crate::preprocess_cifar::{self, CifarPreprocessStages, CIFAR_CHW};

pub const CIFAR10_TEST_LEN: i32 = 10_000;
pub const CIFAR10_TRAIN_LEN: i32 = 50_000;

const RECORD_SIZE: usize = 1 + CIFAR_CHW;

#[derive(Clone, Debug)]
pub struct CifarPreprocessedSample {
    pub index: i32,
    pub label: i32,
    pub shape: Vec<usize>,
    pub fixed: Vec<i32>,
}

#[derive(Error, Debug)]
pub enum CifarLoadError {
    #[error("cifar index out of range: {0}")]
    IndexOutOfRange(i32),
    #[error("cifar binary batches not found under {0} (run Python once to download/export)")]
    RawNotFound(PathBuf),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("parse: {0}")]
    Parse(String),
}

pub fn load_cifar_stages(repo: &Path, index: i32, train: bool) -> Result<CifarPreprocessStages, CifarLoadError> {
    let limit = if train { CIFAR10_TRAIN_LEN } else { CIFAR10_TEST_LEN };
    if !(0..limit).contains(&index) {
        return Err(CifarLoadError::IndexOutOfRange(index));
    }
    let (raw, _label) = load_raw_sample(repo, index as u32, train)?;
    Ok(preprocess_cifar::preprocess_cifar_rgb_chw(&raw))
}

pub fn load_cifar_preprocessed(
    repo: &Path,
    index: i32,
    train: bool,
) -> Result<CifarPreprocessedSample, CifarLoadError> {
    let limit = if train { CIFAR10_TRAIN_LEN } else { CIFAR10_TEST_LEN };
    if !(0..limit).contains(&index) {
        return Err(CifarLoadError::IndexOutOfRange(index));
    }
    let (raw, label) = load_raw_sample(repo, index as u32, train)?;
    let stages = preprocess_cifar::preprocess_cifar_rgb_chw(&raw);
    Ok(CifarPreprocessedSample {
        index,
        label,
        shape: vec![3, 32, 32],
        fixed: stages.fixed,
    })
}

fn cifar_bin_dir(repo: &Path) -> PathBuf {
    let candidates = [
        repo.join("model_training")
            .join("data")
            .join("cifar-10-batches-bin"),
        repo.join("model_training")
            .join("data")
            .join("cifar10")
            .join("cifar-10-batches-bin"),
    ];
    for p in &candidates {
        if p.is_dir() {
            return p.clone();
        }
    }
    candidates[0].clone()
}

fn read_batch_records(path: &Path) -> Result<Vec<Vec<u8>>, CifarLoadError> {
    let bytes = std::fs::read(path).map_err(CifarLoadError::Io)?;
    if bytes.len() % RECORD_SIZE != 0 {
        return Err(CifarLoadError::Parse(format!(
            "batch {} size {} not multiple of {}",
            path.display(),
            bytes.len(),
            RECORD_SIZE
        )));
    }
    let n = bytes.len() / RECORD_SIZE;
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        out.push(bytes[i * RECORD_SIZE..(i + 1) * RECORD_SIZE].to_vec());
    }
    Ok(out)
}

fn load_train_records(dir: &Path) -> Result<Vec<Vec<u8>>, CifarLoadError> {
    let mut all = Vec::with_capacity(50_000);
    for batch in 1..=5 {
        let path = dir.join(format!("data_batch_{batch}.bin"));
        if !path.is_file() {
            return Err(CifarLoadError::RawNotFound(dir.to_path_buf()));
        }
        all.extend(read_batch_records(&path)?);
    }
    Ok(all)
}

fn load_raw_sample(repo: &Path, index: u32, train: bool) -> Result<([u8; CIFAR_CHW], i32), CifarLoadError> {
    let dir = cifar_bin_dir(repo);
    let record = if train {
        let records = load_train_records(&dir)?;
        records
            .get(index as usize)
            .ok_or(CifarLoadError::IndexOutOfRange(index as i32))?
            .clone()
    } else {
        let path = dir.join("test_batch.bin");
        if !path.is_file() {
            return Err(CifarLoadError::RawNotFound(dir));
        }
        let records = read_batch_records(&path)?;
        records
            .get(index as usize)
            .ok_or(CifarLoadError::IndexOutOfRange(index as i32))?
            .clone()
    };
    if record.len() != RECORD_SIZE {
        return Err(CifarLoadError::Parse("record length mismatch".into()));
    }
    let label = record[0] as i32;
    let mut chw = [0u8; CIFAR_CHW];
    // Official bin: R[1024] G[1024] B[1024] row-major planes -> CHW
    for c in 0..3 {
        let plane = &record[1 + c * 1024..1 + (c + 1) * 1024];
        for i in 0..1024 {
            chw[c * 1024 + i] = plane[i];
        }
    }
    Ok((chw, label))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ahe_model_bundle::detect_repo_root;

    #[test]
    fn cifar_index_zero_loads_or_skips_without_data() {
        let repo = detect_repo_root();
        match load_cifar_preprocessed(&repo, 0, false) {
            Ok(s) => {
                assert_eq!(s.shape, vec![3, 32, 32]);
                assert_eq!(s.fixed.len(), CIFAR_CHW);
            }
            Err(CifarLoadError::RawNotFound(_)) => {}
            Err(e) => panic!("unexpected: {e}"),
        }
    }
}
