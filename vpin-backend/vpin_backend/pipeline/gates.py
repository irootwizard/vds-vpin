"""Session / orchestrator gates for dataset ↔ model family and deploy plan."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_CLIENT = _REPO / "vpin-client"
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from vpin_client.hdc.model_decomposer import FAMILY_DATASETS, family_supports_dataset

# model_id → G_family (registry ``network`` field or builtin fallback)
_BUILTIN_FAMILY = {
    "cnn-mnist": "network_a",
    "cnn-mnist-trained": "network_a",
    "cnn-mnist-b": "network_b",
    "lenet-mnist": "lenet_mnist",
    "lenet-cifar10": "lenet_cifar",
    "resnet18-cifar10": "resnet18_cifar",
}

# input shape hint → dataset id
_SHAPE_DATASET = {
    (1, 28, 28): "mnist",
    (3, 32, 32): "cifar10",
}


class DatasetModelMismatchError(ValueError):
    """Raised when dataset / input shape does not match model family (§12)."""


class RangeNotOkError(ValueError):
    """Raised when homomorphic_deploy_plan has range_ok=false."""


def resolve_family(model_id: str, network: str | None = None) -> str:
    if network:
        net = network.lower()
        if net in ("a", "network_a"):
            return "network_a"
        if net in ("b", "network_b"):
            return "network_b"
        if net in ("lenet_cifar", "lenet-cifar"):
            return "lenet_cifar"
        return net
    return _BUILTIN_FAMILY.get(model_id, "network_a")


def infer_dataset_from_shape(shape: list[int] | tuple[int, ...]) -> str | None:
    if len(shape) == 3:
        key = tuple(int(x) for x in shape)
        return _SHAPE_DATASET.get(key)
    if len(shape) == 4 and shape[0] == 1:
        key = tuple(int(x) for x in shape[1:])
        return _SHAPE_DATASET.get(key)
    return None


def assert_dataset_model_compatible(
    *,
    model_id: str,
    network: str | None = None,
    dataset: str | None = None,
    input_shape: list[int] | tuple[int, ...] | None = None,
) -> str:
    """Return resolved family or raise DatasetModelMismatchError."""
    family = resolve_family(model_id, network)
    ds = (dataset or "").lower()
    if not ds and input_shape is not None:
        ds = infer_dataset_from_shape(input_shape) or ""
    if not ds:
        return family
    if not family_supports_dataset(family, ds):
        allowed = sorted(FAMILY_DATASETS.get(family, ()))
        raise DatasetModelMismatchError(
            f"model {model_id!r} (family={family}) cannot serve dataset {ds!r}; "
            f"allowed: {allowed}"
        )
    # Hard reject: Network A on CIFAR
    if family == "network_a" and ds == "cifar10":
        raise DatasetModelMismatchError(
            f"model {model_id!r} (Network A) cannot process CIFAR-10; use lenet-cifar10"
        )
    return family


def load_deploy_plan(weights_dir: Path) -> dict[str, Any] | None:
    path = weights_dir / "homomorphic_deploy_plan.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def assert_range_ok(weights_dir: Path) -> dict[str, Any]:
    plan = load_deploy_plan(weights_dir)
    if plan is None:
        manifest = weights_dir / "ahe_manifest.json"
        if manifest.is_file():
            plan = json.loads(manifest.read_text(encoding="utf-8"))
    if plan is None:
        return {}
    if plan.get("range_ok") is False:
        raise RangeNotOkError(
            f"homomorphic deploy plan range_ok=false for {weights_dir}"
        )
    return plan


def orchestration_from_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Extract LeNet WS orchestration hints from homomorphic_deploy_plan."""
    plan = plan or {}
    out: dict[str, Any] = {}
    skip = plan.get("skip_return_phases")
    if skip is not None:
        out["skip_return_phases"] = skip
    return out
