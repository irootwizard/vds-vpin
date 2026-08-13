"""Truncation plan single source of truth for Network A training and AHE.

Paper / legacy alignment (`src/cnn_networks/Client.py`):
- `shifting(decrypted, bits)` uses `bits` as **from_bits** (current fixed-point scale f),
  not an arbitrary truncate amount. Network A natural scales:
  - after_pool: f = 16 + 4 (sum) + 10 (inv_fp) = 26
  - after_fc1 (pre-shift): f = 16 + 16 (weight) = 32
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FIXED_POINT_BITS = 16
POOL_INV_BITS = 10
# Legacy Client.py / paper artifact — intrinsic representation scales at truncate points.
INTRINSIC_SHIFT_POOL = 26
INTRINSIC_SHIFT_FC1 = 32
DEFAULT_SHIFT_POOL = INTRINSIC_SHIFT_POOL
DEFAULT_SHIFT_FC1 = INTRINSIC_SHIFT_FC1

# BSGS table m=3200000 → searchable magnitude ≈ m² (see vPIN论文与代码对照说明.md §二).
BSGS_M = 3_200_000
BSGS_ABS_SAFE_LIMIT = BSGS_M * BSGS_M - 1
INT32_ABS_SAFE_LIMIT = (1 << 31) - 1
# Conservative homomorphic intermediate guard (below BSGS ceiling).
AHE_ABS_SAFE_LIMIT = 1 << 30

SAFETY_MARGIN_BITS = 2


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
    max_after_pool_pre_shift: float = 0.0
    max_after_fc1_pre_relu: float = 0.0
    max_after_fc2_pre_relu: float = 0.0
    max_post_pool_shift: float = 0.0
    max_post_fc1_shift: float = 0.0
    percentile: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TruncationPlan:
    shift_pool: int = DEFAULT_SHIFT_POOL
    shift_fc1: int = DEFAULT_SHIFT_FC1
    pool_inv_bits: int = POOL_INV_BITS
    fixed_point_bits: int = FIXED_POINT_BITS
    calibration: ActivationStats | None = None

    @property
    def pool_inv_fp(self) -> int:
        return int(round((1.0 / 16.0) * (2**self.pool_inv_bits)))

    def phases(self) -> tuple[TruncationPhase, ...]:
        return (
            TruncationPhase("after_conv", "relu", FIXED_POINT_BITS, FIXED_POINT_BITS),
            TruncationPhase(
                "after_pool",
                "shift",
                self.shift_pool,
                FIXED_POINT_BITS,
                shift_bits=self.shift_pool,
            ),
            TruncationPhase(
                "after_fc1",
                "relu_then_shift",
                self.shift_fc1,
                FIXED_POINT_BITS,
                shift_bits=self.shift_fc1,
            ),
            TruncationPhase("after_fc2", "relu_only", FIXED_POINT_BITS, FIXED_POINT_BITS),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "shift_pool": self.shift_pool,
            "shift_fc1": self.shift_fc1,
            "pool_inv_bits": self.pool_inv_bits,
            "fixed_point_bits": self.fixed_point_bits,
            "pool_inv_fp": self.pool_inv_fp,
            "intrinsic_shift_pool": INTRINSIC_SHIFT_POOL,
            "intrinsic_shift_fc1": INTRINSIC_SHIFT_FC1,
            "phases": [p.to_dict() for p in self.phases()],
        }
        if self.calibration is not None:
            d["calibration"] = self.calibration.to_dict()
        return d

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> TruncationPlan:
        data = json.loads(path.read_text(encoding="utf-8"))
        cal = data.get("calibration")
        calibration = ActivationStats(**cal) if isinstance(cal, dict) else None
        return cls(
            shift_pool=int(data.get("shift_pool", DEFAULT_SHIFT_POOL)),
            shift_fc1=int(data.get("shift_fc1", DEFAULT_SHIFT_FC1)),
            pool_inv_bits=int(data.get("pool_inv_bits", POOL_INV_BITS)),
            fixed_point_bits=int(data.get("fixed_point_bits", FIXED_POINT_BITS)),
            calibration=calibration,
        )


DEFAULT_PLAN = TruncationPlan()


def plan_from_topology() -> TruncationPlan:
    """Read shift bits wired into vpin-backend WS protocol."""
    from vpin_backend.crypto.ahe.topology import NETWORK_A

    pool = next(p.shift_bits for p in NETWORK_A.truncation_phases if p.phase_id == "after_pool")
    fc1 = next(p.shift_bits for p in NETWORK_A.truncation_phases if p.phase_id == "after_fc1")
    return TruncationPlan(shift_pool=int(pool), shift_fc1=int(fc1))


def post_shift_magnitude(pre_shift_max: float, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> float:
    """Magnitude after client shifting(from_bits → to_bits): divide by 2^(from_bits - to_bits)."""
    if pre_shift_max <= 0:
        return 0.0
    return pre_shift_max / (2.0 ** (from_bits - to_bits))


def batch_calibrate_shifts(
    *,
    max_after_pool: float,
    max_after_fc1_pre_relu: float,
    max_after_fc2_pre_relu: float = 0.0,
    n_samples: int = 0,
    percentile: float = 100.0,
) -> TruncationPlan:
    """Batch static-budget calibration (paper §二 + task3 §6).

    shift_bits stay at **intrinsic representation scales** (26/32). Batch scan only
    validates decrypt/re-encrypt safety; it does not lower from_bits (that mis-scales reals).
    """
    stats = ActivationStats(
        n_samples=n_samples,
        max_after_pool_pre_shift=max_after_pool,
        max_after_fc1_pre_relu=max_after_fc1_pre_relu,
        max_after_fc2_pre_relu=max_after_fc2_pre_relu,
        max_post_pool_shift=post_shift_magnitude(max_after_pool, INTRINSIC_SHIFT_POOL),
        max_post_fc1_shift=post_shift_magnitude(max_after_fc1_pre_relu, INTRINSIC_SHIFT_FC1),
        percentile=percentile,
    )
    return TruncationPlan(
        shift_pool=INTRINSIC_SHIFT_POOL,
        shift_fc1=INTRINSIC_SHIFT_FC1,
        calibration=stats,
    )


def calibrate_shifts(
    max_after_pool: float,
    max_after_fc1_pre_relu: float,
) -> TruncationPlan:
    """Backward-compatible wrapper — always returns intrinsic 26/32."""
    return batch_calibrate_shifts(
        max_after_pool=max_after_pool,
        max_after_fc1_pre_relu=max_after_fc1_pre_relu,
        n_samples=0,
    )


def validate_activation_stats(stats: ActivationStats, plan: TruncationPlan | None = None) -> tuple[bool, list[str]]:
    """Check batch calibration against BSGS decrypt ceiling and int32 re-encrypt ceiling."""
    plan = plan or TruncationPlan()
    errors: list[str] = []

    checks = (
        ("after_pool_pre_shift", stats.max_after_pool_pre_shift, BSGS_ABS_SAFE_LIMIT),
        ("after_fc1_pre_relu", stats.max_after_fc1_pre_relu, BSGS_ABS_SAFE_LIMIT),
        ("after_fc2_pre_relu", stats.max_after_fc2_pre_relu, BSGS_ABS_SAFE_LIMIT),
    )
    for name, val, limit in checks:
        if val > 0 and val >= limit:
            errors.append(f"{name} max|x|={val:.0e} exceeds BSGS safe limit {limit:.0e}")

    post_checks = (
        (
            "post_pool_shift",
            post_shift_magnitude(stats.max_after_pool_pre_shift, plan.shift_pool),
            INT32_ABS_SAFE_LIMIT,
        ),
        (
            "post_fc1_shift",
            post_shift_magnitude(stats.max_after_fc1_pre_relu, plan.shift_fc1),
            INT32_ABS_SAFE_LIMIT,
        ),
    )
    for name, val, limit in post_checks:
        if val > 0 and val >= limit:
            errors.append(f"{name} max|x|={val:.0e} exceeds int32 re-encrypt limit {limit:.0e}")

    return len(errors) == 0, errors


def check_bounds(tensor_max_abs: float, layer_name: str, *, limit: int = AHE_ABS_SAFE_LIMIT) -> None:
    if tensor_max_abs >= limit:
        raise ValueError(
            f"{layer_name} max|x|={tensor_max_abs:.0e} exceeds safe limit {limit}"
        )


def load_plan_for_run(run_dir: Path) -> TruncationPlan:
    """Load truncation plan from run dir, falling back to topology defaults."""
    cfg = run_dir / "truncation_config.json"
    if cfg.is_file():
        return TruncationPlan.load(cfg)
    return plan_from_topology()
