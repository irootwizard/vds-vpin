"""Client-side nonlinear ops — relu / shifting (Client.py semantics)."""

from __future__ import annotations

import numpy as np

from vpin_client.crypto.ahe.codec import fixed_point_to_real, real_to_fixed_point


def relu(values: np.ndarray) -> np.ndarray:
    return np.maximum(0, values)


def shifting(decrypted_fixed: np.ndarray, from_bits: int, to_bits: int = 16) -> np.ndarray:
    reals = fixed_point_to_real(decrypted_fixed, from_bits)
    return real_to_fixed_point(reals, to_bits)
