"""Client-side nonlinear ops after decrypt."""

from __future__ import annotations

import numpy as np

from vpin_client.crypto.ahe.codec import fixed_point_to_real, real_to_fixed_point


def relu(values: np.ndarray) -> np.ndarray:
    return np.maximum(0, values)


def shifting(decrypted_fixed: np.ndarray, from_bits: int, to_bits: int = 16) -> np.ndarray:
    reals = fixed_point_to_real(decrypted_fixed, from_bits)
    return real_to_fixed_point(reals, to_bits)


def apply_client_action(
    decrypted: np.ndarray,
    action: str,
    *,
    shift_bits: int | None = None,
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
    raise ValueError(f"unknown client_action: {action}")
