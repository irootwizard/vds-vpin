"""§1 / §11.1 CIFAR-10 RGB adapter  A_cifar_rgb.

Maps a raw CIFAR-10 image ``I ∈ Z^{3×32×32}_[0,255]`` to an encryptable fixed-point
tensor at scale F=16 with **per-image** (all-channel) min-max normalization:

    x̃ = I / 255
    x' = clip( (x̃ - min x̃) / (max x̃ - min x̃), eps_min, eps_max )
    X  = floor( x' · 2^F )            (truncate toward zero, int32)

Crucially this is the **3×32×32 RGB** track — no resize to 28, no grayscale, no
pad to 32 (image is already 32×32). It is NOT the Network-A-compatible cifar28
adapter, and must never be routed to Network A.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from vpin_client.hdc import scale_rules as sr

ADAPTER_ID = "cifar_rgb"
INPUT_SHAPE = (3, 32, 32)
NUM_CLASSES = 10


@dataclass
class AdaptedInput:
    """Result of A_cifar_rgb."""

    raw_uint8: np.ndarray          # (3, 32, 32) uint8
    normalized_float: np.ndarray   # (3, 32, 32) float32 in [eps_min, eps_max]
    fixed_int32: np.ndarray        # (3, 32, 32) int32 at scale F
    digest_hex: str
    max_abs_input: int             # M_in = max|X|
    label: int | None = None
    index: int | None = None
    source: str = "cifar10"

    @property
    def input_safe(self) -> bool:
        """§1 input safety: M_in < L_int32."""
        return self.max_abs_input < sr.INT32_ABS_SAFE_LIMIT


def _to_chw_uint8(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.shape == INPUT_SHAPE:
        chw = arr
    elif arr.shape == (32, 32, 3):  # HWC → CHW
        chw = np.transpose(arr, (2, 0, 1))
    else:
        raise ValueError(f"expected (3,32,32) or (32,32,3) CIFAR image, got {arr.shape}")
    return chw.astype(np.uint8, copy=False)


def adapt_cifar_rgb(
    image: np.ndarray,
    *,
    label: int | None = None,
    index: int | None = None,
    source: str = "cifar10",
) -> AdaptedInput:
    """Apply A_cifar_rgb to a single CIFAR-10 image (CHW or HWC uint8)."""
    raw = _to_chw_uint8(image)
    x = raw.astype(np.float64) / 255.0
    x_min = float(x.min())
    x_max = float(x.max())
    denom = x_max - x_min
    if denom == 0:
        norm = np.full_like(x, 0.5)
    else:
        norm = (x - x_min) / denom
    norm = np.clip(norm, sr.EPS_MIN, sr.EPS_MAX)
    fixed = np.floor(norm * (2**sr.F)).astype(np.int32)

    digest = hashlib.sha256(fixed.tobytes()).hexdigest()
    max_abs = int(np.max(np.abs(fixed.astype(np.int64))))
    return AdaptedInput(
        raw_uint8=raw,
        normalized_float=norm.astype(np.float32),
        fixed_int32=fixed,
        digest_hex=digest,
        max_abs_input=max_abs,
        label=label,
        index=index,
        source=source,
    )


def adapt_cifar_rgb_batch(images: np.ndarray) -> np.ndarray:
    """Vectorized per-image min-max → fixed int32 for (B,3,32,32) uint8/float batch.

    Used by the training preprocess; returns (B,3,32,32) int32 at scale F.
    """
    arr = np.asarray(images)
    if arr.ndim != 4 or arr.shape[1:] != INPUT_SHAPE:
        raise ValueError(f"expected (B,3,32,32), got {arr.shape}")
    x = arr.astype(np.float64)
    if x.max() > 1.0:
        x = x / 255.0
    b = x.shape[0]
    flat = x.reshape(b, -1)
    mn = flat.min(axis=1, keepdims=True)
    mx = flat.max(axis=1, keepdims=True)
    denom = np.where(mx - mn == 0, 1.0, mx - mn)
    norm = (flat - mn) / denom
    norm = np.clip(norm, sr.EPS_MIN, sr.EPS_MAX).reshape(arr.shape[0], *INPUT_SHAPE)
    return np.floor(norm * (2**sr.F)).astype(np.int32)
