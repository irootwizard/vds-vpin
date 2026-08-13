"""Torch preprocessing aligned with vpin_client.data.preprocess."""

from __future__ import annotations

import torch

from vpin_client.data.constants import CLIP_MAX, CLIP_MIN, FIXED_POINT_BITS, PAD_SIZE

PAD_SIZE = PAD_SIZE
FIXED_POINT_BITS = FIXED_POINT_BITS
CLIP_MIN = CLIP_MIN
CLIP_MAX = CLIP_MAX


def pad_to_32x32(x: torch.Tensor) -> torch.Tensor:
    """x: (B, 1, 28, 28) float [0,1] -> (B, 1, 32, 32)."""
    b = x.shape[0]
    out = torch.zeros(b, 1, PAD_SIZE, PAD_SIZE, device=x.device, dtype=x.dtype)
    out[:, :, 2:30, 2:30] = x
    return out


def min_max_scaling_per_image(x: torch.Tensor) -> torch.Tensor:
    """Per-sample min-max on (B,1,H,W), matching numpy preprocess."""
    b = x.shape[0]
    flat = x.reshape(b, -1)
    min_val = flat.min(dim=1, keepdim=True).values
    max_val = flat.max(dim=1, keepdim=True).values
    denom = max_val - min_val
    denom = torch.where(denom == 0, torch.ones_like(denom), denom)
    norm = (flat - min_val) / denom
    norm = torch.clamp(norm, CLIP_MIN, CLIP_MAX)
    return norm.reshape_as(x)


def preprocess_batch_uint8(images: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """
    images: (B, 1, 28, 28) uint8 or float.
    Returns (normalized_float B,1,32,32), (fixed_int32 B,1,32,32).
    """
    if images.dtype == torch.uint8:
        x = images.float() / 255.0
    else:
        x = images.float()
    padded = pad_to_32x32(x)
    normalized = min_max_scaling_per_image(padded)
    scale = 2**FIXED_POINT_BITS
    # Truncate toward zero — matches vpin_client (astype int32, no round).
    fixed = (normalized * scale).to(torch.int32)
    return normalized, fixed


def uint8_to_float_input(images: torch.Tensor) -> torch.Tensor:
    """For float forward: same pad + min-max without int quantization."""
    if images.dtype == torch.uint8:
        x = images.float() / 255.0
    else:
        x = images.float()
    return min_max_scaling_per_image(pad_to_32x32(x))
