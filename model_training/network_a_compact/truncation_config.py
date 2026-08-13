"""Truncation plan for Network A compact (no client shift phases)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from model_training.network_a.truncation_config import (
    BSGS_ABS_SAFE_LIMIT,
    FIXED_POINT_BITS,
    INT32_ABS_SAFE_LIMIT,
    POOL_INV_BITS,
)

POOL_FROM_BITS = FIXED_POINT_BITS + 4 + POOL_INV_BITS  # 26
FC1_FROM_BITS = FIXED_POINT_BITS + FIXED_POINT_BITS  # 32
# Server absorbs baseline pool shift: shift(pool_f26) ≡ sum(4×4)//POOL_COMPACT_DIV.
POOL_COMPACT_DIV = 16
# FC1 MAC at f=32; baseline client shift to f=16 before FC2 — compact absorbs on server for int32.
FC1_TO_FC2_SHIFT_BITS = FIXED_POINT_BITS

QuantMode = Literal["int32", "int64"]


@dataclass(frozen=True)
class CompactPhase:
    phase_id: str
    client_action: str
    shape: tuple[int, ...]
    from_bits: int


COMPACT_PHASES: tuple[CompactPhase, ...] = (
    CompactPhase("after_conv", "relu", (1, 1, 32, 32), FIXED_POINT_BITS),
    CompactPhase("after_fc1", "relu_only", (1, 16), FC1_FROM_BITS),
    CompactPhase("after_fc2", "relu_only", (1, 10), FIXED_POINT_BITS),
)


@dataclass(frozen=True)
class CompactPlan:
    quant_mode: QuantMode = "int32"
    fixed_point_bits: int = FIXED_POINT_BITS
    pool_inv_bits: int = POOL_INV_BITS

    @property
    def pool_inv_fp(self) -> int:
        return int(round((1.0 / 16.0) * (2**self.pool_inv_bits)))

    def phases(self) -> tuple[CompactPhase, ...]:
        return COMPACT_PHASES


INT64_ABS_SAFE_LIMIT = (1 << 63) - 1


def reencrypt_limit(mode: QuantMode) -> int:
    return INT32_ABS_SAFE_LIMIT if mode == "int32" else INT64_ABS_SAFE_LIMIT
