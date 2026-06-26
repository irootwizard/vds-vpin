"""§9 InferenceOrchestrator — preflight gates before AHE WS inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vpin_backend.pipeline.gates import (
    DatasetModelMismatchError,
    RangeNotOkError,
    assert_dataset_model_compatible,
    assert_range_ok,
    load_deploy_plan,
)


@dataclass
class PreflightResult:
    ok: bool
    family: str
    model_id: str
    deployable: bool
    range_ok: bool
    accuracy_ok: bool
    adapter_id: str | None = None
    checkpoints: list[dict[str, Any]] | None = None
    errors: list[str] | None = None


class InferenceOrchestrator:
    """Plan-driven preflight for MNIST Network A and CIFAR LeNet families."""

    def __init__(self, *, weights_dir: Path, model_id: str, network: str | None = None) -> None:
        self.weights_dir = weights_dir.resolve()
        self.model_id = model_id
        self.network = network

    def preflight(
        self,
        *,
        dataset: str | None = None,
        input_shape: list[int] | tuple[int, ...] | None = None,
        require_deployable: bool = False,
    ) -> PreflightResult:
        errors: list[str] = []
        try:
            family = assert_dataset_model_compatible(
                model_id=self.model_id,
                network=self.network,
                dataset=dataset,
                input_shape=input_shape,
            )
        except DatasetModelMismatchError as exc:
            return PreflightResult(
                ok=False,
                family=resolve_family_safe(self.model_id, self.network),
                model_id=self.model_id,
                deployable=False,
                range_ok=False,
                accuracy_ok=False,
                errors=[str(exc)],
            )

        plan = load_deploy_plan(self.weights_dir) or {}
        range_ok = bool(plan.get("range_ok", True))
        accuracy_ok = bool(plan.get("accuracy_ok", True))
        deployable = bool(plan.get("deployable", range_ok and accuracy_ok))

        try:
            if plan:
                assert_range_ok(self.weights_dir)
        except RangeNotOkError as exc:
            errors.append(str(exc))
            range_ok = False
            deployable = False

        if require_deployable and not deployable:
            errors.append("deployable=false in homomorphic_deploy_plan")

        return PreflightResult(
            ok=len(errors) == 0,
            family=family,
            model_id=self.model_id,
            deployable=deployable,
            range_ok=range_ok,
            accuracy_ok=accuracy_ok,
            adapter_id=plan.get("adapter_id"),
            checkpoints=plan.get("checkpoints"),
            errors=errors or None,
        )


def resolve_family_safe(model_id: str, network: str | None) -> str:
    from vpin_backend.pipeline.gates import resolve_family

    return resolve_family(model_id, network)
