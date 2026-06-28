"""Client actions for compact Network A."""

from __future__ import annotations

import numpy as np
import torch

from model_training.network_a.fixed_point import apply_client_action as baseline_apply
from model_training.network_a.truncation_config import INTRINSIC_SHIFT_FC1
from model_training.network_a_compact.truncation_config import QuantMode, reencrypt_limit


def relu_int(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)


def cast_for_reencrypt(x: np.ndarray, mode: QuantMode) -> np.ndarray:
    """Simulate ElGamal re-encrypt plaintext cast."""
    if mode == "int64":
        return x.astype(np.int64, copy=False)
    return x.astype(np.int32)


def apply_client_action(
    x: np.ndarray,
    action: str,
    *,
    quant_mode: QuantMode = "int32",
) -> np.ndarray:
    work = x.astype(np.int64, copy=False)
    if action == "relu":
        out = relu_int(work)
        return cast_for_reencrypt(out, quant_mode)
    if action == "relu_only":
        # Terminal phase — no re-encrypt; keep int64 like baseline Network A.
        return relu_int(work)
    if action == "relu_then_shift":
        shifted = baseline_apply(torch.from_numpy(work), "relu_then_shift", shift_bits_val=INTRINSIC_SHIFT_FC1)
        return cast_for_reencrypt(shifted.numpy(), quant_mode)
    raise ValueError(f"compact network does not support action={action!r}")


def apply_fc1_boundary(x: np.ndarray, *, quant_mode: QuantMode) -> np.ndarray:
    """int32: relu+shift in one client round; int64: relu only (f=32 fits int64 re-encrypt)."""
    if quant_mode == "int32":
        return apply_client_action(x, "relu_then_shift", quant_mode=quant_mode)
    return apply_client_action(x, "relu_only", quant_mode=quant_mode)


def check_reencrypt_range(x: np.ndarray, mode: QuantMode, checkpoint: str) -> None:
    limit = reencrypt_limit(mode)
    m = int(np.max(np.abs(x))) if x.size else 0
    if m > limit:
        raise ValueError(
            f"{checkpoint}: |x|_max={m} exceeds {mode} re-encrypt limit {limit}"
        )
