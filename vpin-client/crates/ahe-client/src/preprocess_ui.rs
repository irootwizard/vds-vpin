//! UI JSON for preprocess gallery (matches vpin_client.data.core.preprocess_result_to_dict shape).

use std::io::Cursor;
use std::path::Path;

use image::{GrayImage, ImageFormat};
use serde_json::{json, Value};

use crate::preprocess_core::{self, PreprocessStages, PAD};
use crate::preprocess_upload::UploadPreprocessError;

const FIXED_POINT_BITS: i32 = 16;

#[derive(Clone, Debug)]
pub struct PreprocessMeta {
    pub source: String,
    pub mnist_index: Option<i32>,
    pub label: Option<i32>,
    pub filename: Option<String>,
}

pub fn official_to_ui_json(repo: &Path, index: i32) -> Result<Value, crate::MnistLoadError> {
    let sample = crate::load_official_preprocessed(repo, index)?;
    let stages = crate::load_official_stages(repo, index)?;
    Ok(stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: "official".into(),
            mnist_index: Some(sample.mnist_index),
            label: Some(sample.label),
            filename: None,
        },
    ))
}

pub fn official_batch_to_ui_json(
    repo: &Path,
    start: u32,
    count: u32,
) -> Result<Value, crate::MnistLoadError> {
    let mut items = Vec::new();
    let end = start.saturating_add(count).min(10_000);
    for i in start..end {
        items.push(official_to_ui_json(repo, i as i32)?);
    }
    Ok(json!({ "items": items }))
}

pub fn upload_path_to_ui_json(path: &Path) -> Result<Value, UploadPreprocessError> {
    let (stages, filename) = crate::preprocess_upload_path(path)?;
    Ok(stages_to_ui_json(
        &stages,
        PreprocessMeta {
            source: "upload".into(),
            mnist_index: None,
            label: None,
            filename: Some(filename),
        },
    ))
}

pub fn stages_to_ui_json(stages: &PreprocessStages, meta: PreprocessMeta) -> Value {
    let digest = preprocess_core::input_digest_hex(&stages.fixed);
    let shape = vec![1, 1, PAD, PAD];
    json!({
        "source": meta.source,
        "mnist_index": meta.mnist_index,
        "label": meta.label,
        "upload_id": null,
        "filename": meta.filename,
        "input_digest_hex": digest,
        "preview_png_base64": gray_preview_b64(&stages.raw_uint8, 28, 28),
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
