"""Client-side nonlinear ops after decrypt."""

from __future__ import annotations

import numpy as np

from vpin_client.crypto.ahe.codec import fixed_point_to_real, real_to_fixed_point


def relu(values: np.ndarray) -> np.ndarray:
    return np.maximum(0, values)


def shifting(decrypted_fixed: np.ndarray, from_bits: int, to_bits: int = 16) -> np.ndarray:
    reals = fixed_point_to_real(decrypted_fixed, from_bits)
    return real_to_fixed_point(reals, to_bits)


def max_pool_2d(x: np.ndarray, kernel_size: int = 2, stride: int = 2) -> np.ndarray:
    """2D max pool over (batch, ch, H, W) fixed-point tensor."""
    batch, ch, H, W = x.shape
    out_H = (H - kernel_size) // stride + 1
    out_W = (W - kernel_size) // stride + 1
    out = np.empty((batch, ch, out_H, out_W), dtype=x.dtype)
    for b in range(batch):
        for c in range(ch):
            for i in range(out_H):
                for j in range(out_W):
                    out[b, c, i, j] = x[
                        b, c,
                        i * stride : i * stride + kernel_size,
                        j * stride : j * stride + kernel_size,
                    ].max()
    return out


def apply_client_action(
    decrypted: np.ndarray,
    action: str,
    *,
    shift_bits: int | None = None,
    pool_kernel: int = 2,
) -> np.ndarray:
    if action == "relu":
        return relu(decrypted)
    if action == "shift":
        if shift_bits is None:
            raise ValueError("shift_bits required")
        return shifting(decrypted, shift_bits)
    if action == "relu_then_shift":
        if shift_bits is None:
            raise ValueError("shift_bits required")
        return shifting(relu(decrypted), shift_bits)
    if action == "relu_only":
        return relu(decrypted)
    if action == "relu_pool_shift":
        if shift_bits is None:
            raise ValueError("shift_bits required")
        return shifting(max_pool_2d(relu(decrypted), pool_kernel, pool_kernel), shift_bits)
    if action == "logits_only":
        return decrypted
    raise ValueError(f"unknown client_action: {action}")
