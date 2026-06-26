"""Shared vPIN image preprocessing core (Network A input pipeline)."""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass

import numpy as np

from vpin_client.data.constants import CLIP_MAX, CLIP_MIN, FIXED_POINT_BITS, PAD_SIZE

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


@dataclass
class PreprocessResult:
    raw_uint8: np.ndarray
    padded_float: np.ndarray
    normalized_float: np.ndarray
    fixed_int32: np.ndarray
    label: int | None = None
    mnist_index: int | None = None
    source: str = "unknown"
    upload_id: str | None = None
    filename: str | None = None


def min_max_scaling(images: np.ndarray) -> np.ndarray:
    min_val = np.min(images)
    max_val = np.max(images)
    if max_val == min_val:
        return np.full_like(images, 0.5, dtype=np.float32)
    normalized = (images - min_val) / (max_val - min_val)
    return np.clip(normalized, CLIP_MIN, CLIP_MAX).astype(np.float32)


def pad_to_32x32(x_f: np.ndarray) -> np.ndarray:
    """x_f: (28,28) float in [0,1] -> (1,1,32,32)."""
    out = np.zeros((1, 1, PAD_SIZE, PAD_SIZE), dtype=np.float32)
    out[0, 0, 2:30, 2:30] = x_f
    return out


def preprocess_uint8_28x28(
    raw: np.ndarray,
    *,
    label: int | None = None,
    index: int | None = None,
    source: str = "unknown",
    upload_id: str | None = None,
    filename: str | None = None,
) -> PreprocessResult:
    if raw.shape != (28, 28):
        raise ValueError(f"expected (28,28), got {raw.shape}")
    x_f = raw.astype(np.float32) / 255.0
    padded = pad_to_32x32(x_f)
    normalized = min_max_scaling(padded)
    fixed = (normalized * (2**FIXED_POINT_BITS)).astype(np.int32)
    return PreprocessResult(
        raw_uint8=raw.astype(np.uint8),
        padded_float=padded,
        normalized_float=normalized,
        fixed_int32=fixed,
        label=label,
        mnist_index=index,
        source=source,
        upload_id=upload_id,
        filename=filename,
    )


def compute_input_digest(fixed_int32: np.ndarray) -> str:
    return hashlib.sha256(fixed_int32.tobytes()).hexdigest()


def preview_png_base64(result: PreprocessResult, stage: str = "raw") -> str:
    if Image is None:
        return ""
    buf = io.BytesIO()
    if stage == "raw":
        Image.fromarray(result.raw_uint8, mode="L").save(buf, format="PNG")
    elif stage == "padded":
        pad = result.padded_float[0, 0] if result.padded_float.ndim == 4 else result.padded_float
        Image.fromarray((pad * 255).astype(np.uint8), mode="L").save(buf, format="PNG")
    else:  # normalized
        norm = result.normalized_float[0, 0] if result.normalized_float.ndim == 4 else result.normalized_float
        Image.fromarray((norm * 255).astype(np.uint8), mode="L").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def preprocess_trace_dict(result: PreprocessResult) -> list[dict]:
    """UI-friendly preprocessing stages with tensor stats and previews."""
    digest = compute_input_digest(result.fixed_int32)
    fixed = result.fixed_int32
    return [
        {
            "id": "prep_raw",
            "category": "预处理",
            "title": "原始图像",
            "summary": f"shape=(28,28) dtype=uint8",
            "detail": {
                "stage": "raw",
                "shape": [28, 28],
                "dtype": "uint8",
                "min": int(result.raw_uint8.min()),
                "max": int(result.raw_uint8.max()),
                "preview_png_base64": preview_png_base64(result, "raw"),
            },
        },
        {
            "id": "prep_padded",
            "category": "预处理",
            "title": "零填充 32×32",
            "summary": "居中 pad，边缘填 0",
            "detail": {
                "stage": "padded",
                "shape": list(result.padded_float.shape),
                "dtype": "float32",
                "min": float(result.padded_float.min()),
                "max": float(result.padded_float.max()),
                "preview_png_base64": preview_png_base64(result, "padded"),
            },
        },
        {
            "id": "prep_normalized",
            "category": "预处理",
            "title": "Min-Max 归一化",
            "summary": f"range [{result.normalized_float.min():.4f}, {result.normalized_float.max():.4f}]",
            "detail": {
                "stage": "normalized",
                "shape": list(result.normalized_float.shape),
                "dtype": "float32",
                "min": float(result.normalized_float.min()),
                "max": float(result.normalized_float.max()),
                "mean": float(result.normalized_float.mean()),
                "preview_png_base64": preview_png_base64(result, "normalized"),
            },
        },
        {
            "id": "prep_fixed",
            "category": "预处理",
            "title": "定点化 Q16",
            "summary": f"shape={list(fixed.shape)} dtype=int32",
            "detail": {
                "stage": "fixed",
                "shape": list(fixed.shape),
                "dtype": "int32",
                "fixed_point_bits": FIXED_POINT_BITS,
                "min": int(fixed.min()),
                "max": int(fixed.max()),
                "sample": fixed.flatten()[:8].tolist(),
            },
        },
        {
            "id": "prep_digest",
            "category": "预处理",
            "title": "输入摘要 SHA256",
            "summary": digest[:16] + "...",
            "detail": {
                "input_digest_hex": digest,
                "algorithm": "SHA256",
                "payload": "fixed_int32.tobytes()",
            },
        },
    ]


def preprocess_result_to_dict(result: PreprocessResult) -> dict:
    return {
        "source": result.source,
        "mnist_index": result.mnist_index,
        "label": result.label,
        "upload_id": result.upload_id,
        "filename": result.filename,
        "input_digest_hex": compute_input_digest(result.fixed_int32),
        "preview_png_base64": preview_png_base64(result),
        "fixed_shape": list(result.fixed_int32.shape),
        "preprocess_trace": preprocess_trace_dict(result),
    }
