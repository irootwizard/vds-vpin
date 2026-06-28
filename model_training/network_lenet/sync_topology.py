"""Sync the backend LeNet-CIFAR topology truncation phases when calibration differs.

LeNet-CIFAR uses formula-derived intrinsic scales (pool=28, fc=32). If a future
backend ``LENET_CIFAR`` topology exists in ``vpin_backend.crypto.ahe.topology`` this
helper validates the wired shift bits; otherwise it is a no-op (P2 has no homomorphic
LeNet engine yet — §11.9).
"""

from __future__ import annotations

from model_training.network_lenet.truncation_config import SHIFT_FC, SHIFT_POOL, TruncationPlan


def sync_topology_if_needed(plan: TruncationPlan) -> bool:
    """Return True if the backend topology matched/was updated; False if absent."""
    try:
        from vpin_backend.crypto.ahe.topology import get_topology

        topo = get_topology("lenet_cifar")
    except (KeyError, ImportError):
        return False

    wired_pool = next(
        (p.shift_bits for p in topo.truncation_phases if p.phase_id == "after_pool1"), None
    )
    wired_fc = next(
        (p.shift_bits for p in topo.truncation_phases if p.phase_id == "after_fc1"), None
    )
    return wired_pool == plan.shift_pool == SHIFT_POOL and wired_fc == plan.shift_fc == SHIFT_FC
