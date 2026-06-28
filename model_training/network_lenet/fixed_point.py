"""Fixed-point client ops for LeNet-CIFAR (matches AHE client truncate actions).

Identical semantics to ``network_a.fixed_point`` (legacy ``Client.shifting``):
``shift`` uses ``from_bits`` as the current fixed-point scale f.
"""

from __future__ import annotations

import torch

from model_training.network_lenet.truncation_config import FIXED_POINT_BITS


def relu_int(x: torch.Tensor) -> torch.Tensor:
    return torch.clamp(x, min=0)


def shift_bits(x: torch.Tensor, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> torch.Tensor:
    """TReLU shift: divide by 2^from_bits then re-quantize to to_bits."""
    reals = x.to(torch.float64) / (2.0**from_bits)
    return (reals * (2.0**to_bits)).to(torch.int64)


def apply_client_action(
    x: torch.Tensor,
    action: str,
    *,
    shift_bits_val: int | None = None,
    to_bits: int = FIXED_POINT_BITS,
) -> torch.Tensor:
    work = x.to(torch.int64)
    if action == "relu":
        return relu_int(work)
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
