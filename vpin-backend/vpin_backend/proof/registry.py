"""ProofPlan registry: model_id → run_dir + schedule mode."""

from __future__ import annotations

from pathlib import Path

from vpin_backend.proof.proof_plan import ProofPlan

REPO = Path(__file__).resolve().parents[3]
STANDARD_NETWORK_A_RUN = REPO / "model_training" / "outputs" / "20260622_184254"

_REGISTRY: dict[str, tuple[Path, str]] = {
    "A": (STANDARD_NETWORK_A_RUN, "paper_proof"),
    "cnn-mnist-trained-20260622_184254": (STANDARD_NETWORK_A_RUN, "paper_proof"),
}


def register_proof_plan(model_id: str, run_dir: Path, schedule_mode: str = "paper_proof") -> None:
    _REGISTRY[model_id] = (run_dir.resolve(), schedule_mode)


def resolve_run_dir(model_id: str, run_dir: Path | None = None) -> Path:
    if run_dir is not None:
        return run_dir.resolve()
    if model_id not in _REGISTRY:
        raise KeyError(f"no ProofPlan registered for model_id={model_id!r}")
    return _REGISTRY[model_id][0]


def load_proof_plan(
    model_id: str,
    *,
    run_dir: Path | None = None,
    schedule_mode: str | None = None,
) -> ProofPlan:
    path = resolve_run_dir(model_id, run_dir)
    mode = schedule_mode or _REGISTRY.get(model_id, (path, "paper_proof"))[1]
    return ProofPlan.from_run_dir(path, model_id=model_id, mode=mode)


def resolve_proof_plan(model_id: str, run_dir: Path | None = None) -> ProofPlan:
    return load_proof_plan(model_id, run_dir=run_dir)


def default_run_dir(model_id: str) -> Path | None:
    entry = _REGISTRY.get(model_id)
    return entry[0] if entry else None
