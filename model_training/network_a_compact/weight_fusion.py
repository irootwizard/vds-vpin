"""Export standard int64 FC weights for Network A compact (no per-weight fusion)."""

from __future__ import annotations

import numpy as np

from model_training.network_a_compact.truncation_config import FIXED_POINT_BITS, POOL_COMPACT_DIV

# Homomorphic pool→FC1 server path: pool f=26 then MAC >> POOL_SHIFT_BITS ≈ sum//16 @ W.
POOL_SHIFT_BITS = 10
FC1_ACCUM_SHIFT = 1 << POOL_SHIFT_BITS


def quantize_fc_weight(w: np.ndarray) -> np.ndarray:
    return (w.astype(np.float64) * (2**FIXED_POINT_BITS)).astype(np.int64)


def pool_sum_div16(after_conv: np.ndarray) -> np.ndarray:
    """Server-side pool absorbing client shift: sum(4×4)//POOL_COMPACT_DIV ≡ shift(pool_f26)."""
    h, w = after_conv.shape
    pooled = np.zeros((h // 4, w // 4), dtype=np.int64)
    for i in range(pooled.shape[0]):
        for j in range(pooled.shape[1]):
            pooled[i, j] = (
                np.sum(after_conv[i * 4 : (i + 1) * 4, j * 4 : (j + 1) * 4], dtype=np.int64)
                // POOL_COMPACT_DIV
            )
    return pooled.reshape(1, -1)


def export_compact_bundle(
    *,
    weight_fc1: np.ndarray,
    bias_fc1: np.ndarray,
    weight_fc2: np.ndarray,
    bias_fc2: np.ndarray,
) -> dict[str, np.ndarray]:
    return {
        "weight_fc1_64_16.npy": quantize_fc_weight(weight_fc1),
        "bias_fc1_16.npy": quantize_fc_weight(bias_fc1),
        "weight_fc2_16_10.npy": quantize_fc_weight(weight_fc2),
        "bias_fc2_10.npy": quantize_fc_weight(bias_fc2),
    }
