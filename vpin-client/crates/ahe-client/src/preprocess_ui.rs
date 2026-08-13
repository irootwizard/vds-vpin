//! UI JSON for preprocess gallery (matches vpin_client.data.core.preprocess_result_to_dict shape).

use std::io::Cursor;
use std::path::Path;

use image::{GrayImage, ImageFormat, RgbImage};
use serde_json::{json, Value};

use crate::cifar10_official::{self, CifarLoadError};
use crate::preprocess_cifar::{self, CIFAR_CHW, CIFAR_SIDE};
use crate::preprocess_core::{self, PreprocessStages, PAD};
use crate::preprocess_upload::UploadPreprocessError;

const FIXED_POINT_BITS: i32 = 16;

#[derive(Clone, Debug)]
pub struct PreprocessMeta {
    pub source: String,
    pub dataset_id: String,
    pub sample_index: Option<i32>,
    pub mnist_index: Option<i32>,
    pub label: Option<i32>,
    pub filename: Option<String>,
    pub preview_kind: &'static str,
}

pub fn official_to_ui_json(repo: &Path, index: i32) -> Result<Value, crate::MnistLoadError> {
    let sample = crate::load_official_preprocessed(repo, index)?;
    let stages = crate::load_official_stages(repo, index)?;
    Ok(stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: "official".into(),
            dataset_id: "mnist-test".into(),
            sample_index: Some(sample.mnist_index),
            mnist_index: Some(sample.mnist_index),
            label: Some(sample.label),
            filename: None,
            preview_kind: "grayscale",
        },
    ))
}

pub fn official_batch_to_ui_json(
    repo: &Path,
    start: u32,
    count: u32,
) -> Result<Value, crate::MnistLoadError> {
    dataset_batch_to_ui_json(repo, "mnist-test", start, count).map_err(|e| match e {
        DatasetPreviewError::Mnist(m) => m,
        DatasetPreviewError::Cifar(_) | DatasetPreviewError::Unsupported(_) => {
            crate::MnistLoadError::Parse("batch failed".into())
        }
    })
}

pub fn dataset_to_ui_json(repo: &Path, dataset_id: &str, index: i32) -> Result<Value, DatasetPreviewError> {
    match dataset_id {
        "mnist-test" => official_to_ui_json(repo, index).map_err(DatasetPreviewError::Mnist),
        "mnist-train" => mnist_split_to_ui_json(repo, index, true).map_err(DatasetPreviewError::Mnist),
        "cifar10-test" => cifar_to_ui_json(repo, index, false).map_err(DatasetPreviewError::Cifar),
        "cifar10-train" => cifar_to_ui_json(repo, index, true).map_err(DatasetPreviewError::Cifar),
        other => Err(DatasetPreviewError::Unsupported(other.to_string())),
    }
}

pub fn dataset_batch_to_ui_json(
    repo: &Path,
    dataset_id: &str,
    start: u32,
    count: u32,
) -> Result<Value, DatasetPreviewError> {
    let limit = dataset_limit(dataset_id);
    let end = start.saturating_add(count).min(limit);
    let mut items = Vec::new();
    for i in start..end {
        items.push(dataset_to_ui_json(repo, dataset_id, i as i32)?);
    }
    Ok(json!({ "items": items }))
}

fn dataset_limit(dataset_id: &str) -> u32 {
    match dataset_id {
        "mnist-train" => 60_000,
        "cifar10-test" => 10_000,
        "cifar10-train" => 50_000,
        _ => 10_000,
    }
}

#[derive(Debug, thiserror::Error)]
pub enum DatasetPreviewError {
    #[error(transparent)]
    Mnist(#[from] crate::MnistLoadError),
    #[error(transparent)]
    Cifar(#[from] CifarLoadError),
    #[error("unsupported dataset: {0}")]
    Unsupported(String),
}

fn mnist_split_to_ui_json(repo: &Path, index: i32, train: bool) -> Result<Value, crate::MnistLoadError> {
    let sample = crate::load_mnist_preprocessed(repo, index, train)?;
    let stages = crate::load_mnist_stages(repo, index, train)?;
    Ok(stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: if train { "mnist-train".into() } else { "official".into() },
            dataset_id: if train { "mnist-train".into() } else { "mnist-test".into() },
            sample_index: Some(sample.mnist_index),
            mnist_index: Some(sample.mnist_index),
            label: Some(sample.label),
            filename: None,
            preview_kind: "grayscale",
        },
    ))
}

fn cifar_to_ui_json(repo: &Path, index: i32, train: bool) -> Result<Value, CifarLoadError> {
    let sample = cifar10_official::load_cifar_preprocessed(repo, index, train)?;
    let stages = cifar10_official::load_cifar_stages(repo, index, train)?;
    Ok(cifar_stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: if train { "cifar10-train".into() } else { "cifar10-test".into() },
            dataset_id: if train { "cifar10-train".into() } else { "cifar10-test".into() },
            sample_index: Some(sample.index),
            mnist_index: None,
            label: Some(sample.label),
            filename: None,
            preview_kind: "rgb",
        },
        sample.index,
    ))
}

pub fn cifar_stages_to_ui_json(
    stages: &preprocess_cifar::CifarPreprocessStages,
    meta: PreprocessMeta,
    index: i32,
) -> Value {
    let digest = preprocess_cifar::cifar_input_digest_hex(&stages.fixed);
    json!({
        "source": meta.source,
        "dataset_id": meta.dataset_id,
        "sample_index": meta.sample_index,
        "cifar_index": index,
        "mnist_index": meta.mnist_index,
        "label": meta.label,
        "upload_id": null,
        "filename": meta.filename,
        "input_digest_hex": digest,
        "preview_png_base64": rgb_chw_preview_b64(&stages.raw_chw),
        "preview_kind": meta.preview_kind,
        "fixed_shape": [3, CIFAR_SIDE, CIFAR_SIDE],
    })
}

pub fn upload_path_to_ui_json(path: &Path) -> Result<Value, UploadPreprocessError> {
    let (stages, filename) = crate::preprocess_upload_path(path)?;
    Ok(stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: "upload".into(),
            dataset_id: "user-upload-image".into(),
            sample_index: None,
            mnist_index: None,
            label: None,
            filename: Some(filename),
            preview_kind: "grayscale",
        },
    ))
}

pub fn stages_to_ui_json(stages: &PreprocessStages, meta: PreprocessMeta) -> Value {
    let digest = preprocess_core::input_digest_hex(&stages.fixed);
    let shape = vec![1, 1, PAD, PAD];
    json!({
        "source": meta.source,
        "dataset_id": meta.dataset_id,
        "sample_index": meta.sample_index,
        "mnist_index": meta.mnist_index,
        "label": meta.label,
        "upload_id": null,
        "filename": meta.filename,
        "input_digest_hex": digest,
        "preview_png_base64": gray_preview_b64(&stages.raw_uint8, 28, 28),
        "preview_kind": meta.preview_kind,
        "fixed_shape": shape,
        "preprocess_trace": preprocess_trace_dict(stages, &digest),
    })
}

fn preprocess_trace_dict(stages: &PreprocessStages, digest: &str) -> Vec<Value> {
    let padded_min = stages.padded.iter().copied().fold(f32::INFINITY, f32::min);
    let padded_max = stages.padded.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let norm_min = stages.normalized.iter().copied().fold(f32::INFINITY, f32::min);
    let norm_max = stages.normalized.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let norm_mean = stages.normalized.iter().sum::<f32>() / stages.normalized.len() as f32;
    let fixed_min = *stages.fixed.iter().min().unwrap_or(&0);
    let fixed_max = *stages.fixed.iter().max().unwrap_or(&0);
    let sample: Vec<i32> = stages.fixed.iter().take(8).copied().collect();
    vec![
        json!({
            "id": "prep_raw",
            "category": "预处理",
            "title": "原始图像",
            "summary": "shape=(28,28) dtype=uint8",
            "detail": {
                "stage": "raw",
                "shape": [28, 28],
                "dtype": "uint8",
                "min": stages.raw_uint8.iter().min().copied().unwrap_or(0),
                "max": stages.raw_uint8.iter().max().copied().unwrap_or(0),
                "preview_png_base64": gray_preview_b64(&stages.raw_uint8, 28, 28),
            }
        }),
        json!({
            "id": "prep_padded",
            "category": "预处理",
            "title": "零填充 32×32",
            "summary": "居中 pad，边缘填 0",
            "detail": {
                "stage": "padded",
                "shape": [1, 1, PAD, PAD],
                "dtype": "float32",
                "min": padded_min,
                "max": padded_max,
                "preview_png_base64": float_grid_preview_b64(&stages.padded, PAD as u32),
            }
        }),
        json!({
            "id": "prep_normalized",
            "category": "预处理",
            "title": "Min-Max 归一化",
            "summary": format!("range [{norm_min:.4}, {norm_max:.4}]"),
            "detail": {
                "stage": "normalized",
                "shape": [1, 1, PAD, PAD],
                "dtype": "float32",
                "min": norm_min,
                "max": norm_max,
                "mean": norm_mean,
                "preview_png_base64": float_grid_preview_b64(&stages.normalized, PAD as u32),
            }
        }),
        json!({
            "id": "prep_fixed",
            "category": "预处理",
            "title": "定点化 Q16",
            "summary": format!("shape=[1, 1, {PAD}, {PAD}] dtype=int32"),
            "detail": {
                "stage": "fixed",
                "shape": [1, 1, PAD, PAD],
                "dtype": "int32",
                "fixed_point_bits": FIXED_POINT_BITS,
                "min": fixed_min,
                "max": fixed_max,
                "sample": sample,
            }
        }),
        json!({
            "id": "prep_digest",
            "category": "预处理",
            "title": "输入摘要 SHA256",
            "summary": format!("{}...", &digest[..16.min(digest.len())]),
            "detail": {
                "input_digest_hex": digest,
                "algorithm": "SHA256",
                "payload": "fixed_int32.tobytes()",
            }
        }),
    ]
}

fn gray_preview_b64(pixels: &[u8], width: u32, height: u32) -> String {
    let img = GrayImage::from_raw(width, height, pixels.to_vec()).unwrap_or_else(|| {
        GrayImage::new(width, height)
    });
    encode_png_b64(&img)
}

fn float_grid_preview_b64(data: &[f32], side: u32) -> String {
    let pixels: Vec<u8> = data
        .iter()
        .map(|v| (v.clamp(0.0, 1.0) * 255.0) as u8)
        .collect();
    gray_preview_b64(&pixels, side, side)
}

fn rgb_chw_preview_b64(chw: &[u8; CIFAR_CHW]) -> String {
    let mut rgb = RgbImage::new(CIFAR_SIDE as u32, CIFAR_SIDE as u32);
    for y in 0..CIFAR_SIDE {
        for x in 0..CIFAR_SIDE {
            let i = y * CIFAR_SIDE + x;
            let r = chw[i];
            let g = chw[1024 + i];
            let b = chw[2048 + i];
            rgb.put_pixel(x as u32, y as u32, image::Rgb([r, g, b]));
        }
    }
    encode_png_b64_rgb(&rgb)
}

fn encode_png_b64_rgb(img: &RgbImage) -> String {
    let mut buf = Vec::new();
    if img
        .write_to(&mut Cursor::new(&mut buf), ImageFormat::Png)
        .is_err()
    {
        return String::new();
    }
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &buf)
}

fn encode_png_b64(img: &GrayImage) -> String {
    let mut buf = Vec::new();
    if img
        .write_to(&mut Cursor::new(&mut buf), ImageFormat::Png)
        .is_err()
    {
        return String::new();
    }
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &buf)
}
