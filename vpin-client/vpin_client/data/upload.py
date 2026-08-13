"""Client-side image upload preprocessing — plaintext never sent to server."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from vpin_client.data.core import PreprocessResult, preprocess_uint8_28x28

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def _uint8_28x28_from_pil(img: "Image.Image") -> np.ndarray:
    if img.mode != "L":
        img = img.convert("L")
    if img.size != (28, 28):
        img = img.resize((28, 28), Image.Resampling.LANCZOS)
    # MNIST convention: dark digit on light background → invert for pipeline
    return (255 - np.array(img, dtype=np.uint8)).astype(np.uint8)


def preprocess_upload_path(path: Path | str) -> PreprocessResult:
    if Image is None:
        raise ImportError("Pillow is required for upload preprocessing")
    p = Path(path)
    with Image.open(p) as img:
        raw = _uint8_28x28_from_pil(img)
    return preprocess_uint8_28x28(
        raw,
        source="upload",
        filename=p.name,
    )


def preprocess_upload_bytes(data: bytes, *, filename: str = "upload") -> PreprocessResult:
    if Image is None:
        raise ImportError("Pillow is required for upload preprocessing")
    with Image.open(io.BytesIO(data)) as img:
        raw = _uint8_28x28_from_pil(img)
    return preprocess_uint8_28x28(
        raw,
        source="upload",
        filename=filename,
    )
