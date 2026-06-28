"""HDC §4–§6: range / magnitude propagation and per-checkpoint safety.

Given a ``LayerGraph`` and a calibration max table ``M_pre[π_k]`` (max |activation|
before each checkpoint shift, §7), decide BSGS / int32 safety per checkpoint and the
overall ``range_ok`` predicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vpin_client.hdc import scale_rules as sr
from vpin_client.hdc.layer_ir import LayerGraph, LayerNode


@dataclass
class CheckpointRange:
    id: str
    client_op: str
    from_bits: int
    to_bits: int
    is_shift: bool
    m_pre: float          # max |x| before shift (calibration)
    m_post: float         # max |x| after shift (only meaningful for shift ops)
    bsgs_ok: bool         # m_pre < L_BSGS  (decryptable)
    int32_ok: bool        # m_post < L_int32 (re-encryptable; shift ops only)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "client_op": self.client_op,
            "from_bits": self.from_bits,
            "to_bits": self.to_bits,
            "is_shift": self.is_shift,
            "m_pre": self.m_pre,
            "m_post": self.m_post,
            "bsgs_ok": self.bsgs_ok,
            "int32_ok": self.int32_ok,
        }


@dataclass
class RangeReport:
    checkpoints: list[CheckpointRange]
    range_ok: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "range_ok": self.range_ok,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "errors": list(self.errors),
        }


def checkpoint_range(node: LayerNode, m_pre: float) -> CheckpointRange:
    """§6–§7 safety for one checkpoint given its calibrated pre-shift magnitude."""
    is_shift = node.is_shift
    if is_shift:
        m_post = sr.post_shift_magnitude(m_pre, node.f_in, node.f_out)
    else:
        m_post = m_pre
    bsgs_ok = m_pre < sr.BSGS_ABS_SAFE_LIMIT
    int32_ok = (m_post < sr.INT32_ABS_SAFE_LIMIT) if is_shift else True
    return CheckpointRange(
        id=node.checkpoint or node.name,
        client_op=node.client_op or "",
        from_bits=node.f_in,
        to_bits=node.f_out,
        is_shift=is_shift,
        m_pre=float(m_pre),
        m_post=float(m_post),
        bsgs_ok=bool(bsgs_ok),
        int32_ok=bool(int32_ok),
    )


def propagate_ranges(graph: LayerGraph, m_pre_table: dict[str, float]) -> RangeReport:
    """Compute per-checkpoint safety and ``range_ok = ∧ bsgs ∧ (shift→int32)`` (§7)."""
    rows: list[CheckpointRange] = []
    errors: list[str] = []
    for node in graph.checkpoints():
        cp_id = node.checkpoint or node.name
        m_pre = float(m_pre_table.get(cp_id, 0.0))
        row = checkpoint_range(node, m_pre)
        rows.append(row)
        if not row.bsgs_ok:
            errors.append(
                f"{cp_id}: pre-shift max {row.m_pre:.3e} ≥ BSGS limit {sr.BSGS_ABS_SAFE_LIMIT:.3e}"
            )
        if row.is_shift and not row.int32_ok:
            errors.append(
                f"{cp_id}: post-shift max {row.m_post:.3e} ≥ int32 re-encrypt limit "
                f"{sr.INT32_ABS_SAFE_LIMIT:.3e}"
            )
    range_ok = all(r.bsgs_ok for r in rows) and all(
        r.int32_ok for r in rows if r.is_shift
    )
    return RangeReport(checkpoints=rows, range_ok=range_ok, errors=errors)


def static_fc_bound(
    *,
    fan_in: int,
    m_pre_input_post_shift: float,
    max_abs_weight_fp: int,
    max_abs_bias_fp: int,
) -> float:
    """§6 weight-only static FC magnitude bound:

        B_fc = d · M_input_post_shift · max|Ŵ| + max|b̂|
    """
    return fan_in * m_pre_input_post_shift * max_abs_weight_fp + max_abs_bias_fp
