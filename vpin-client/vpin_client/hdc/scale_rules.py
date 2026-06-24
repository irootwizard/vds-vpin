"""HDC §2–§3 scale-propagation rules (single source of truth for fixed-point scales).

The compiler derives every checkpoint's ``from_bits`` from these rules — never hand
written. Both :mod:`vpin_client.hdc.layer_ir` (formula side) and the model-training
``truncation_config`` modules (actual side) consume the same helpers so the
``verify`` closed loop (§13) can assert ``formula == actual``.

Global constants (§ symbols)::

    F          = 16        # target fixed-point fractional bits
    EPS_MIN    = 0.001     # min-max clip floor
    EPS_MAX    = 0.9999999 # min-max clip ceiling
    L_BSGS     = m^2 - 1   # decryptable magnitude (m = 3.2e6)
    L_INT32    = 2^31 - 1  # int32 re-encrypt ceiling
    TAU        = 0.001     # accuracy tolerance

Scale rules (§3, op -> f_out)::

    encrypt                                   -> F
    conv_Z / ReLU                             -> f_in        (scale preserving)
    sum_pool_{k×k} (× 2^inv_bits fixed inv)   -> f_in + log2(k^2) + inv_bits
    FC (weights quantized at F)               -> f_in + F
    client_shift(f_in -> f_out)               -> f_out (usually F)
"""

from __future__ import annotations

import math

FIXED_POINT_BITS = 16
F = FIXED_POINT_BITS

EPS_MIN = 0.001
EPS_MAX = 0.9999999

# BSGS table m = 3.2e6 → searchable magnitude ≈ m^2 (see vPIN 论文与代码对照说明 §二).
BSGS_M = 3_200_000
BSGS_ABS_SAFE_LIMIT = BSGS_M * BSGS_M - 1
INT32_ABS_SAFE_LIMIT = (1 << 31) - 1

ACCURACY_TOLERANCE = 0.001  # τ


def encrypt_scale() -> int:
    """encrypt: raw fixed-point input lives at scale F."""
    return F


def conv_relu_scale(f_in: int) -> int:
    """conv_Z / ReLU preserve the incoming fixed-point scale (§3)."""
    return f_in


def sum_pool_scale(f_in: int, k: int, inv_bits: int) -> int:
    """sum_pool_{k×k} followed by a fixed-point inverse multiply.

    The k×k summation adds ``log2(k^2)`` magnitude bits and the fixed inverse
    (``inv_fp`` represented at ``inv_bits``) adds ``inv_bits`` fractional bits, so

        f_out = f_in + log2(k^2) + inv_bits

    For LeNet-CIFAR (k=2, inv_bits=10): 16 + 2 + 10 = 28  (the **2×2** variant —
    must NOT reuse Network A's 4×4 ``26``).
    For Network A     (k=4, inv_bits=10): the engine folds an extra 1/k^2 into
    ``inv_fp`` (see ``sum_pool_avg_scale``) so its checkpoint is ``26``.
    """
    log2_k2 = int(round(math.log2(k * k)))
    return f_in + log2_k2 + inv_bits


def sum_pool_avg_scale(f_in: int, inv_bits: int) -> int:
    """Average-pool variant where ``inv_fp = 2^inv_bits / k^2`` cancels the k^2 magnitude.

    Used by Network A (4×4): f_out = f_in + inv_bits = 26.
    """
    return f_in + inv_bits


def fc_scale(f_in: int) -> int:
    """FC with weights quantized at F adds F fractional bits: f_out = f_in + F (§3)."""
    return f_in + F


def client_shift_scale(f_out: int = F) -> int:
    """client_shift / client_relu_shift retarget to f_out (default F)."""
    return f_out


def pool_inv_fp(k: int, inv_bits: int, *, average: bool) -> int:
    """Fixed-point inverse multiplier applied by the (sum) pool op.

    average=True  → ``round(2^inv_bits / k^2)`` (Network A 4×4 → 64, keeps scale at
                    f_in + inv_bits).
    average=False → ``2^inv_bits`` (LeNet 2×2 sum variant; the k^2 magnitude lifts
                    the scale to f_in + log2(k^2) + inv_bits = 28, and after the
                    client shift the real value recovered is the window mean).
    """
    if average:
        return int(round((2**inv_bits) / (k * k)))
    return int(2**inv_bits)


def post_shift_magnitude(pre_shift_max: float, from_bits: int, to_bits: int = F) -> float:
    """Magnitude after client shifting(from_bits → to_bits): /2^(from_bits - to_bits)."""
    if pre_shift_max <= 0:
        return 0.0
    return pre_shift_max / (2.0 ** (from_bits - to_bits))


def trunc_ulp_real(to_bits: int = F) -> float:
    """Per-element real truncation error bound after shift: ≤ 0.5 / 2^to_bits (§4)."""
    return 0.5 / (2**to_bits)
