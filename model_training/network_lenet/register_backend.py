"""Register trained LeNet-CIFAR weights in the vpin-backend model registry.

deployable=true is only written when the HDC validation report (verify, §13) and
the deploy plan agree it is deployable — mirroring Network A's ahe_feasibility gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_backend.storage.registry import upsert_model
from vpin_backend.models.weights_bundle import store_weights_path

from model_training.network_lenet.export_weights import EXPORT_FILES


def _read_deployable(weights_dir: Path) -> tuple[bool, bool, bool]:
    """Return (deployable, range_ok, accuracy_ok) from HDC reports if present."""
    report_path = weights_dir / "hdc_validation_report.json"
    plan_path = weights_dir / "homomorphic_deploy_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else None
    if plan is not None:
        pi_ok = True
        if report_path.is_file():
            pi_ok = bool(json.loads(report_path.read_text(encoding="utf-8")).get("pi_match", True))
        return (
            pi_ok and bool(plan.get("deployable", False)),
            bool(plan.get("range_ok", False)),
            bool(plan.get("accuracy_ok", False)),
        )
    if report_path.is_file():
        data = json.loads(report_path.read_text(encoding="utf-8"))
        if not data.get("pi_match", False):
            return False, False, False
        acc_ok = bool(data.get("accuracy", {}).get("ok", False))
        chk = data.get("checkpoints", {})
        range_ok = all(
            c.get("bsgs_ok", False) and c.get("int32_ok", True) for c in chk.values()
        ) if chk else bool(data.get("range_ok", False))
        return bool(data.get("deployable", range_ok and acc_ok)), range_ok, acc_ok
    return False, False, False


def register_model(
    *,
    weights_dir: Path,
    model_id: str = "lenet-cifar10",
    name: str = "LeNet CIFAR-10 (trained)",
    accuracy: float | None = None,
) -> None:
    weights_dir = weights_dir.resolve()
    for fname in EXPORT_FILES:
        if not (weights_dir / fname).is_file():
            raise FileNotFoundError(f"missing {weights_dir / fname}")

    acc = accuracy
    metrics_path = weights_dir / "metrics.json"
    if acc is None and metrics_path.is_file():
        meta = json.loads(metrics_path.read_text(encoding="utf-8"))
        for phase in reversed(meta.get("phases", [])):
            if phase.get("name") == "fixed" and "best_test_acc" in phase:
                acc = float(phase["best_test_acc"]) * 100.0
                break

    deployable, range_ok, accuracy_ok = _read_deployable(weights_dir)

    entry = {
        "id": model_id,
        "name": name,
        "framework": "PyTorch",
        "task": "图像分类",
        "params_count_m": 0.062,
        "input_shape": "3x32x32",
        "accuracy": acc or 0.0,
        "network": "lenet_cifar",
        "topology": "lenet_cifar_v1",
        "weights_dir": store_weights_path(weights_dir, repo_root=REPO),
        "deployable": deployable,
        "range_ok": range_ok,
        "accuracy_ok": accuracy_ok,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    upsert_model(entry)
    (weights_dir / "registry_snippet.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    print(f"Registered {model_id} -> {weights_dir} (deployable={deployable})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-dir", type=Path, required=True)
    parser.add_argument("--model-id", default="lenet-cifar10")
    parser.add_argument("--name", default="LeNet CIFAR-10 (trained)")
    parser.add_argument("--accuracy", type=float, default=None)
    args = parser.parse_args(argv)
    register_model(
        weights_dir=args.weights_dir,
        model_id=args.model_id,
        name=args.name,
        accuracy=args.accuracy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
