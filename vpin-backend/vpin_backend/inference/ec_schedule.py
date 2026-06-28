"""Load paper-derived EC witness counts (PtMul / PtAdd) for Network A."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from vpin_backend.config import get_settings

STANDARD_RUN = "model_training/outputs/20260622_184254"
_MODE = "paper_proof"


@dataclass(frozen=True)
class EcWitnessCounts:
    num_pt_mul: int
    num_pt_add: int
    source: str


def _repo_root() -> Path:
    return get_settings().repo_root.resolve()


def _schedule_paths(run_dir: Path | None) -> list[Path]:
    root = _repo_root()
    candidates: list[Path] = []
    if run_dir is not None:
        candidates.append(run_dir / "proof_artifacts" / "ec_witness_schedule.json")
    candidates.append(root / STANDARD_RUN / "proof_artifacts" / "ec_witness_schedule.json")
    return candidates


def _load_json_schedule(path: Path) -> EcWitnessCounts | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sched = data.get("schedules", {}).get(_MODE)
    if not sched:
        return None
    try:
        rel = path.relative_to(_repo_root())
        src = str(rel)
    except ValueError:
        src = str(path)
    return EcWitnessCounts(
        num_pt_mul=int(sched["total_pt_mul"]),
        num_pt_add=int(sched["total_pt_add"]),
        source=src,
    )


def _derive_via_module() -> EcWitnessCounts:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from model_training.network_a.ec_witness_schedule import (  # noqa: WPS433
        EcWitnessMode,
        derive_paper_proof_schedule,
    )

    sched = derive_paper_proof_schedule()
    return EcWitnessCounts(
        num_pt_mul=sched.total_pt_mul,
        num_pt_add=sched.total_pt_add,
        source="model_training.network_a.ec_witness_schedule (derived)",
    )


def load_paper_proof_counts(
    network: str = "A",
    *,
    run_dir: Path | None = None,
) -> EcWitnessCounts:
    """Return Table I paper_proof PtMul/PtAdd totals for *network*."""
    net = network.upper()
    if net != "A":
        return EcWitnessCounts(num_pt_mul=0, num_pt_add=0, source="unsupported network")

    for path in _schedule_paths(run_dir):
        loaded = _load_json_schedule(path)
        if loaded is not None:
            return loaded

    return _derive_via_module()
