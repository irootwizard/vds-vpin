"""HDC §7–§8: Compile → HomomorphicDeployPlan P (homomorphic_deploy_plan.json).

    P = ( G, Π, {M_pre, M_post, BSGS_k, INT32_k}_k, A_id, deployable )

``deployable ⇔ range_ok ∧ accuracy_ok`` (§7). The plan is produced by the
model-training ``ahe_feasibility`` / ``compile_deploy_plan`` step and written next
to the exported weights so the backend import hook (§8) can surface it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vpin_client.hdc import scale_rules as sr
from vpin_client.hdc.layer_ir import LayerGraph
from vpin_client.hdc.range_propagate import RangeReport, propagate_ranges


@dataclass
class HomomorphicDeployPlan:
    model_id: str
    family: str
    adapter_id: str
    input_shape: list[int]
    graph: dict[str, Any]                 # G (layer_ir.to_dict)
    checkpoints: list[dict[str, Any]]     # Π with per-k M_pre/M_post/BSGS/INT32
    range_ok: bool
    accuracy_ok: bool
    deployable: bool
    accuracy: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)
    constants: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "HomomorphicDeployPlan":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def compile_deploy_plan(
    *,
    model_id: str,
    graph: LayerGraph,
    m_pre_table: dict[str, float],
    accuracy: dict[str, Any] | None = None,
    accuracy_ok: bool | None = None,
    calibration: dict[str, Any] | None = None,
) -> HomomorphicDeployPlan:
    """Compile(weights→G, Π, D) → P (§7 CompileLeNetCIFAR / §8 product).

    ``m_pre_table``: max |activation| before each checkpoint shift over calibration D.
    ``accuracy_ok``: explicit override; otherwise derived from ``accuracy['ok']``.
    """
    rng: RangeReport = propagate_ranges(graph, m_pre_table)
    accuracy = accuracy or {}
    if accuracy_ok is None:
        accuracy_ok = bool(accuracy.get("ok", False))

    deployable = rng.range_ok and accuracy_ok

    return HomomorphicDeployPlan(
        model_id=model_id,
        family=graph.family,
        adapter_id=graph.adapter_id,
        input_shape=list(graph.input_shape),
        graph=graph.to_dict(),
        checkpoints=[c.to_dict() for c in rng.checkpoints],
        range_ok=rng.range_ok,
        accuracy_ok=bool(accuracy_ok),
        deployable=bool(deployable),
        accuracy=dict(accuracy),
        calibration=dict(calibration or {}),
        constants={
            "F": sr.F,
            "eps_min": sr.EPS_MIN,
            "eps_max": sr.EPS_MAX,
            "bsgs_limit": sr.BSGS_ABS_SAFE_LIMIT,
            "int32_limit": sr.INT32_ABS_SAFE_LIMIT,
            "tau": sr.ACCURACY_TOLERANCE,
        },
        errors=list(rng.errors),
    )


def write_deploy_plan(plan: HomomorphicDeployPlan, path: Path) -> None:
    plan.save(path)
