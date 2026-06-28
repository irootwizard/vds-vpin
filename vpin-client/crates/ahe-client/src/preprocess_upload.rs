//! Client-side image upload preprocessing (Rust lane).

use std::path::{Path, PathBuf};

use image::imageops::FilterType;
use thiserror::Error;

use crate::preprocess_core::{self, PreprocessStages};

#[derive(Error, Debug)]
pub enum UploadPreprocessError {
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("image decode: {0}")]
    Decode(String),
}

pub fn preprocess_upload_path(path: &Path) -> Result<(PreprocessStages, String), UploadPreprocessError> {
    let filename = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("upload")
        .to_string();
    let img = image::open(path).map_err(|e| UploadPreprocessError::Decode(e.to_string()))?;
    let raw = uint8_28x28_from_image(&img);
    Ok((preprocess_core::preprocess_uint8_28x28(&raw), filename))
}

fn uint8_28x28_from_image(img: &image::DynamicImage) -> [u8; 784] {
    let gray = img.to_luma8();
    let resized = if gray.width() != 28 || gray.height() != 28 {
        image::imageops::resize(&gray, 28, 28, FilterType::Lanczos3)
    } else {
        gray
    };
    let mut out = [0u8; 784];
    for y in 0..28u32 {
        for x in 0..28u32 {
            // MNIST convention: dark digit on light background → invert for pipeline
            out[(y * 28 + x) as usize] =
                255u8.saturating_sub(resized.get_pixel(x, y).0[0]);
        }
    }
    out
}

pub fn preprocess_upload_bytes(data: &[u8], filename: &str) -> Result<(PreprocessStages, String), UploadPreprocessError> {
    let img = image::load_from_memory(data).map_err(|e| UploadPreprocessError::Decode(e.to_string()))?;
    let raw = uint8_28x28_from_image(&img);
    Ok((preprocess_core::preprocess_uint8_28x28(&raw), filename.to_string()))
}

#[allow(dead_code)]
pub fn path_display(p: &Path) -> PathBuf {
    p.to_path_buf()
}
