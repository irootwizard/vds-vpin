"""Fixed-point ops matching AHE client truncate actions."""

from __future__ import annotations

import torch

from model_training.network_a.truncation_config import FIXED_POINT_BITS, TruncationPlan


def relu_int(x: torch.Tensor) -> torch.Tensor:
    return torch.clamp(x, min=0)


def shift_bits(x: torch.Tensor, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> torch.Tensor:
    """TReLU shift: divide by 2^from_bits then re-quantize to to_bits (legacy shifting())."""
    scale_down = 2.0**from_bits
    scale_up = 2.0**to_bits
    reals = x.to(torch.float64) / scale_down
    return (reals * scale_up).to(torch.int32)


def apply_client_action(
    x: torch.Tensor,
    action: str,
    *,
    shift_bits_val: int | None = None,
    to_bits: int = FIXED_POINT_BITS,
) -> torch.Tensor:
    """Client nonlinear ops — preserve int64 until shifting produces f=16 int32 for re-encrypt."""
    work = x.to(torch.int64)
    if action == "relu":
        return relu_int(work).to(torch.int32)
    if action == "shift":
        if shift_bits_val is None:
            raise ValueError("shift_bits required")
        return shift_bits(work, shift_bits_val, to_bits)
    if action == "relu_then_shift":
        if shift_bits_val is None:
            raise ValueError("shift_bits required")
        return shift_bits(relu_int(work), shift_bits_val, to_bits)
    if action == "relu_only":
        return relu_int(work)
    raise ValueError(f"unknown action: {action}")
