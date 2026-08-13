"""CIFAR-10 RGB preprocessing for LeNet-CIFAR — torch mirror of A_cifar_rgb (§11.1).

Per-image (all-channel) min-max on 3×32×32, clip to [eps_min, eps_max], floor to
int32 at scale F=16. No resize / grayscale / pad (image is already 32×32 RGB).
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[2]
_CLIENT = _REPO / "vpin-client"
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from vpin_client.hdc import scale_rules as sr

FIXED_POINT_BITS = sr.F
CLIP_MIN = sr.EPS_MIN
CLIP_MAX = sr.EPS_MAX
INPUT_SHAPE = (3, 32, 32)


def min_max_scaling_per_image(x: torch.Tensor) -> torch.Tensor:
    """Per-sample min-max over all channels on (B,3,32,32)."""
    b = x.shape[0]
    flat = x.reshape(b, -1)
    min_val = flat.min(dim=1, keepdim=True).values
    max_val = flat.max(dim=1, keepdim=True).values
    denom = max_val - min_val
    denom = torch.where(denom == 0, torch.ones_like(denom), denom)
    norm = (flat - min_val) / denom
    norm = torch.clamp(norm, CLIP_MIN, CLIP_MAX)
    return norm.reshape_as(x)


def rgb_to_float_input(images: torch.Tensor) -> torch.Tensor:
    """uint8/float (B,3,32,32) → normalized float (per-image min-max), no quantization."""
    if images.dtype == torch.uint8:
        x = images.float() / 255.0
    else:
        x = images.float()
        if float(x.max()) > 1.0:
            x = x / 255.0
    return min_max_scaling_per_image(x)


def preprocess_batch_rgb(images: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Returns (normalized_float B,3,32,32), (fixed_int B,3,32,32 at f=16)."""
    normalized = rgb_to_float_input(images)
    scale = 2**FIXED_POINT_BITS
    # Truncate toward zero (floor for non-negative reals) — matches numpy adapter.
    fixed = torch.floor(normalized * scale).to(torch.int64)
    return normalized, fixed


# Backward-compatible aliases
preprocess_batch_cifar = preprocess_batch_rgb
float_input_cifar = rgb_to_float_input
