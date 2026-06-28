"""Sync topology.py shift_bits when calibration differs from default."""

from __future__ import annotations

import re
from pathlib import Path

from model_training.network_a.truncation_config import (
    DEFAULT_SHIFT_FC1,
    DEFAULT_SHIFT_POOL,
    TruncationPlan,
)

TOPOLOGY_PATH = (
    Path(__file__).resolve().parents[2]
    / "vpin-backend"
    / "vpin_backend"
    / "crypto"
    / "ahe"
    / "topology.py"
)


def sync_topology_if_needed(plan: TruncationPlan) -> bool:
    """Update topology.py truncation phases if shift bits changed. Returns True if patched."""
    if plan.shift_pool == DEFAULT_SHIFT_POOL and plan.shift_fc1 == DEFAULT_SHIFT_FC1:
        return False
    if not TOPOLOGY_PATH.is_file():
        return False

    text = TOPOLOGY_PATH.read_text(encoding="utf-8")
    new_text = text
    new_text = re.sub(
        r'(TruncationPhase\("after_pool", "shift", )\d+(, \(1, 64\)\))',
        rf"\g<1>{plan.shift_pool}\2",
        new_text,
    )
    new_text = re.sub(
        r'(TruncationPhase\("after_fc1", "relu_then_shift", )\d+(, \(1, 16\)\))',
        rf"\g<1>{plan.shift_fc1}\2",
        new_text,
    )
    if new_text != text:
        TOPOLOGY_PATH.write_text(new_text, encoding="utf-8")
        return True
    return False
