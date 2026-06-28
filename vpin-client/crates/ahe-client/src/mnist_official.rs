//! Official MNIST test set (indices 0..9999) — Rust preprocess lane (mnist_official).

use std::io::Read;
use std::path::{Path, PathBuf};

use thiserror::Error;

use crate::preprocess_core::{self, PreprocessStages, PAD};

pub const MNIST_TEST_LEN: i32 = 10_000;

#[derive(Clone, Debug)]
pub struct PreprocessedSample {
    pub mnist_index: i32,
    pub label: i32,
    pub shape: Vec<usize>,
    pub fixed: Vec<i32>,
}

#[derive(Error, Debug)]
pub enum MnistLoadError {
    #[error("mnist index out of range: {0} (valid 0..9999)")]
    IndexOutOfRange(i32),
    #[error("mnist raw files not found under {0} (run Python once to download MNIST)")]
    RawNotFound(PathBuf),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("parse: {0}")]
    Parse(String),
}

pub fn load_official_stages(repo: &Path, index: i32) -> Result<PreprocessStages, MnistLoadError> {
    if !(0..MNIST_TEST_LEN).contains(&index) {
        return Err(MnistLoadError::IndexOutOfRange(index));
    }
    let (image, _label) = load_raw_sample(repo, index as u32)?;
    Ok(preprocess_core::preprocess_uint8_28x28(&image))
}

pub fn load_official_preprocessed(repo: &Path, index: i32) -> Result<PreprocessedSample, MnistLoadError> {
    if !(0..MNIST_TEST_LEN).contains(&index) {
        return Err(MnistLoadError::IndexOutOfRange(index));
    }
    let (image, label) = load_raw_sample(repo, index as u32)?;
    let stages = preprocess_core::preprocess_uint8_28x28(&image);
    Ok(PreprocessedSample {
        mnist_index: index,
        label,
        shape: vec![1, 1, PAD, PAD],
        fixed: stages.fixed,
    })
}

fn mnist_raw_dir(repo: &Path) -> PathBuf {
    repo.join("model_training").join("data").join("MNIST").join("raw")
}

fn resolve_raw_file(dir: &Path, stem: &str) -> Option<PathBuf> {
    for name in [stem, &format!("{stem}.gz")] {
        let p = dir.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

fn read_file_bytes(path: &Path) -> Result<Vec<u8>, std::io::Error> {
    if path.extension().and_then(|s| s.to_str()) == Some("gz") {
        use flate2::read::GzDecoder;
        let raw = std::fs::read(path)?;
        let mut dec = GzDecoder::new(raw.as_slice());
        let mut out = Vec::new();
        dec.read_to_end(&mut out)?;
        Ok(out)
    } else {
        std::fs::read(path)
    }
}

fn load_raw_sample(repo: &Path, index: u32) -> Result<([u8; 784], i32), MnistLoadError> {
    let dir = mnist_raw_dir(repo);
    let images_path = resolve_raw_file(&dir, "t10k-images-idx3-ubyte")
        .ok_or_else(|| MnistLoadError::RawNotFound(dir.clone()))?;
    let labels_path = resolve_raw_file(&dir, "t10k-labels-idx1-ubyte")
        .ok_or_else(|| MnistLoadError::RawNotFound(dir))?;

    let images = read_file_bytes(&images_path).map_err(MnistLoadError::Io)?;
    let labels = read_file_bytes(&labels_path).map_err(MnistLoadError::Io)?;

    let img_off = 16 + (index as usize) * 784;
    if images.len() < img_off + 784 {
        return Err(MnistLoadError::Parse(format!(
            "image idx {index} out of file bounds"
        )));
    }
    let mut image = [0u8; 784];
    image.copy_from_slice(&images[img_off..img_off + 784]);

    let lbl_off = 8 + index as usize;
    if labels.len() <= lbl_off {
        return Err(MnistLoadError::Parse(format!(
            "label idx {index} out of file bounds"
        )));
    }
    Ok((image, labels[lbl_off] as i32))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ahe_model_bundle::detect_repo_root;

    #[test]
    fn official_index_zero_loads_or_skips_without_data() {
        let repo = detect_repo_root();
        match load_official_preprocessed(&repo, 0) {
            Ok(s) => {
                assert_eq!(s.shape, vec![1, 1, 32, 32]);
                assert_eq!(s.fixed.len(), 1024);
            }
            Err(MnistLoadError::RawNotFound(_)) => {}
            Err(e) => panic!("unexpected: {e}"),
        }
    }
}
