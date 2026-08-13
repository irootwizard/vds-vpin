"""Truncation plan for LeNet-CIFAR10 — AHE homomorphic aligned.

Scale table (§11.4 of plan):
- F = 16  (input fixed-point bits)
- POOL_INV_BITS = 10, POOL_K = 2 (2×2 pool window)
- pool inv_fp = 2^POOL_INV_BITS = 1024  (scale-F summand → f = F + log2(k²) + inv_bits)
- After 2×2 pool:  f = 16 + log2(4) + 10 = 28
- After FC (weight at scale F):  f = F + F = 32

Checkpoint table (π1–π6):
  π1: after_conv1  — relu,           f=16 → 16
  π2: after_pool1  — shift,          f=28 → 16
  π3: after_conv2  — relu,           f=16 → 16
  π4: after_pool2  — shift,          f=28 → 16
  π5: after_fc1    — relu_then_shift, f=32 → 16
  π6: after_fc2    — relu_then_shift, f=32 → 16

Note: fc3 output is at f=32; argmax is taken directly (no client round-trip).

NOTE: This file is self-contained (no vpin_client.hdc imports). The formula values
are derived analytically:
  pool_scale = F + log2(k^2) + inv_bits = 16 + 2 + 10 = 28
  fc_scale   = F + F = 32
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ── global fixed-point constants ──────────────────────────────────────────────
FIXED_POINT_BITS: int = 16         # F  — input quantization scale
POOL_INV_BITS: int = 10            # exponent for pool fixed-point inverse
POOL_K: int = 2                    # pool window size (2×2)

# CIFAR LeNet 2×2 pool scale (formula): f = F + log₂(k²) + inv_bits
INTRINSIC_SHIFT_POOL: int = FIXED_POINT_BITS + int(math.log2(POOL_K ** 2)) + POOL_INV_BITS  # = 28
# FC scale (formula): f = F + F
INTRINSIC_SHIFT_FC: int = FIXED_POINT_BITS * 2   # = 32

DEFAULT_SHIFT_POOL: int = INTRINSIC_SHIFT_POOL
DEFAULT_SHIFT_FC: int = INTRINSIC_SHIFT_FC

# Convenience alias matching the older TruncationPlan field name used by other modules
SHIFT_POOL: int = INTRINSIC_SHIFT_POOL
SHIFT_FC: int = INTRINSIC_SHIFT_FC

# BSGS table m=3200000 → searchable magnitude ≈ m².
BSGS_M: int = 3_200_000
BSGS_ABS_SAFE_LIMIT: int = BSGS_M * BSGS_M - 1
INT32_ABS_SAFE_LIMIT: int = (1 << 31) - 1
AHE_ABS_SAFE_LIMIT: int = 1 << 30

SAFETY_MARGIN_BITS: int = 2

# Ordered checkpoint ids
CHECKPOINT_IDS = (
    "after_conv1",
    "after_pool1",
    "after_conv2",
    "after_pool2",
    "after_fc1",
    "after_fc2",
)


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TruncationPhase:
    phase_id: str
    client_action: str
    from_bits: int
    to_bits: int
    shift_bits: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["shift_bits"] is None:
            del d["shift_bits"]
        return d


@dataclass
class ActivationStats:
    """Batch-scan stats over calibration images (per-image min-max, not batch-global)."""

    n_samples: int = 0
    max_after_conv1: float = 0.0
    max_after_pool1_pre_shift: float = 0.0
    max_after_conv2: float = 0.0
    max_after_pool2_pre_shift: float = 0.0
    max_after_fc1_pre_relu: float = 0.0
    max_after_fc2_pre_relu: float = 0.0
    max_post_pool1_shift: float = 0.0
    max_post_pool2_shift: float = 0.0
    max_post_fc1_shift: float = 0.0
    max_post_fc2_shift: float = 0.0
    percentile: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def m_pre_table(self) -> dict[str, float]:
        return {
            "after_conv1": self.max_after_conv1,
            "after_pool1": self.max_after_pool1_pre_shift,
            "after_conv2": self.max_after_conv2,
            "after_pool2": self.max_after_pool2_pre_shift,
            "after_fc1": self.max_after_fc1_pre_relu,
            "after_fc2": self.max_after_fc2_pre_relu,
        }


@dataclass(frozen=True)
class TruncationPlan:
    shift_pool: int = DEFAULT_SHIFT_POOL   # 28 — both pool1 and pool2
    shift_fc: int = DEFAULT_SHIFT_FC       # 32 — both fc1 and fc2 (renamed from shift_fc1/2)
    pool_inv_bits: int = POOL_INV_BITS
    pool_k: int = POOL_K
    fixed_point_bits: int = FIXED_POINT_BITS
    calibration: ActivationStats | None = None

    # Convenience aliases for code expecting shift_fc1 / shift_fc2
    @property
    def shift_fc1(self) -> int:
        return self.shift_fc

    @property
    def shift_fc2(self) -> int:
        return self.shift_fc

    @property
    def pool_inv_fp(self) -> int:
        """inv_fp = 2^inv_bits (full, NOT /k²) → f = F + log₂(k²) + inv_bits = 28."""
        return int(2 ** self.pool_inv_bits)

    def phases(self) -> tuple[TruncationPhase, ...]:
        F = self.fixed_point_bits
        return (
            TruncationPhase("after_conv1", "relu",            F,              F),
            TruncationPhase("after_pool1", "shift",           self.shift_pool, F, shift_bits=self.shift_pool),
            TruncationPhase("after_conv2", "relu",            F,              F),
            TruncationPhase("after_pool2", "shift",           self.shift_pool, F, shift_bits=self.shift_pool),
            TruncationPhase("after_fc1",   "relu_then_shift", self.shift_fc,   F, shift_bits=self.shift_fc),
            TruncationPhase("after_fc2",   "relu_then_shift", self.shift_fc,   F, shift_bits=self.shift_fc),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "model_family": "lenet_cifar",
            "shift_pool": self.shift_pool,
            "shift_fc": self.shift_fc,
            "pool_inv_bits": self.pool_inv_bits,
            "pool_k": self.pool_k,
            "pool_inv_fp": self.pool_inv_fp,
            "fixed_point_bits": self.fixed_point_bits,
            "intrinsic_shift_pool": INTRINSIC_SHIFT_POOL,
            "intrinsic_shift_fc": INTRINSIC_SHIFT_FC,
            "phases": [p.to_dict() for p in self.phases()],
        }
        if self.calibration is not None:
            d["calibration"] = self.calibration.to_dict()
        return d

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TruncationPlan":
        data = json.loads(path.read_text(encoding="utf-8"))
        cal = data.get("calibration")
        calibration = ActivationStats(**{
            k: v for k, v in cal.items()
            if k in ActivationStats.__dataclass_fields__
        }) if isinstance(cal, dict) else None
        # support both shift_fc and shift_fc1 field names
        shift_fc = int(data.get("shift_fc", data.get("shift_fc1", DEFAULT_SHIFT_FC)))
        return cls(
            shift_pool=int(data.get("shift_pool", DEFAULT_SHIFT_POOL)),
            shift_fc=shift_fc,
            pool_inv_bits=int(data.get("pool_inv_bits", POOL_INV_BITS)),
            pool_k=int(data.get("pool_k", POOL_K)),
            fixed_point_bits=int(data.get("fixed_point_bits", FIXED_POINT_BITS)),
            calibration=calibration,
        )


DEFAULT_PLAN = TruncationPlan()


def post_shift_magnitude(pre_shift_max: float, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> float:
    """Magnitude after client shift(from_bits → to_bits): divide by 2^(from_bits - to_bits)."""
    if pre_shift_max <= 0:
        return 0.0
    return pre_shift_max / (2.0 ** (from_bits - to_bits))


def batch_calibrate_shifts(
    *,
    max_after_pool1: float,
    max_after_pool2: float,
    max_after_fc1_pre_relu: float,
    max_after_fc2_pre_relu: float = 0.0,
    n_samples: int = 0,
    percentile: float = 100.0,
) -> TruncationPlan:
    """Batch static-budget calibration (shift_bits stay at intrinsic 28/32)."""
    stats = ActivationStats(
        n_samples=n_samples,
        max_after_pool1_pre_shift=max_after_pool1,
        max_after_pool2_pre_shift=max_after_pool2,
        max_after_fc1_pre_relu=max_after_fc1_pre_relu,
        max_after_fc2_pre_relu=max_after_fc2_pre_relu,
        max_post_pool1_shift=post_shift_magnitude(max_after_pool1, INTRINSIC_SHIFT_POOL),
        max_post_pool2_shift=post_shift_magnitude(max_after_pool2, INTRINSIC_SHIFT_POOL),
        max_post_fc1_shift=post_shift_magnitude(max_after_fc1_pre_relu, INTRINSIC_SHIFT_FC),
        max_post_fc2_shift=post_shift_magnitude(max_after_fc2_pre_relu, INTRINSIC_SHIFT_FC),
        percentile=percentile,
    )
    return TruncationPlan(
        shift_pool=INTRINSIC_SHIFT_POOL,
        shift_fc=INTRINSIC_SHIFT_FC,
        calibration=stats,
    )


def validate_activation_stats(stats: ActivationStats, plan: TruncationPlan | None = None) -> tuple[bool, list[str]]:
    """Check batch calibration against BSGS/int32 safety limits."""
    plan = plan or TruncationPlan()
    errors: list[str] = []

    bsgs_checks = (
        ("after_pool1_pre_shift", stats.max_after_pool1_pre_shift),
        ("after_pool2_pre_shift", stats.max_after_pool2_pre_shift),
        ("after_fc1_pre_relu",    stats.max_after_fc1_pre_relu),
        ("after_fc2_pre_relu",    stats.max_after_fc2_pre_relu),
    )
    for name, val in bsgs_checks:
        if val > 0 and val >= BSGS_ABS_SAFE_LIMIT:
            errors.append(f"{name} max|x|={val:.0e} exceeds BSGS safe limit {BSGS_ABS_SAFE_LIMIT:.0e}")

    post_checks = (
        ("post_pool1_shift", post_shift_magnitude(stats.max_after_pool1_pre_shift, plan.shift_pool)),
        ("post_pool2_shift", post_shift_magnitude(stats.max_after_pool2_pre_shift, plan.shift_pool)),
        ("post_fc1_shift",   post_shift_magnitude(stats.max_after_fc1_pre_relu,    plan.shift_fc)),
    )
    for name, val in post_checks:
        if val > 0 and val >= INT32_ABS_SAFE_LIMIT:
            errors.append(f"{name} max|x|={val:.0e} exceeds int32 re-encrypt limit {INT32_ABS_SAFE_LIMIT:.0e}")

    return len(errors) == 0, errors


def check_bounds(tensor_max_abs: float, layer_name: str, *, limit: int = AHE_ABS_SAFE_LIMIT) -> None:
    if tensor_max_abs >= limit:
        raise ValueError(f"{layer_name} max|x|={tensor_max_abs:.0e} exceeds safe limit {limit}")
