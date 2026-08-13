"""Register trained weights in vpin-backend model registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_backend.storage.registry import upsert_model
from vpin_backend.models.weights_bundle import store_weights_path


def register_model(
    *,
    weights_dir: Path,
    model_id: str = "cnn-mnist-trained",
    name: str = "CNN MNIST Network A (trained)",
    accuracy: float | None = None,
) -> None:
    weights_dir = weights_dir.resolve()
    for fname in (
        "weight_fc1_64_16.npy",
        "bias_fc1_16.npy",
        "weight_fc2_16_10.npy",
        "bias_fc2_10.npy",
    ):
        if not (weights_dir / fname).is_file():
            raise FileNotFoundError(f"missing {weights_dir / fname}")

    acc = accuracy
    metrics_path = weights_dir / "metrics.json"
    if acc is None and metrics_path.is_file():
        meta = json.loads(metrics_path.read_text(encoding="utf-8"))
        ev = meta.get("evaluation") or {}
        if "fixed_acc" in ev:
            acc = float(ev["fixed_acc"]) * 100.0
        else:
            for phase in reversed(meta.get("phases", [])):
                if phase.get("name") == "fixed" and "best_test_acc" in phase:
                    acc = float(phase["best_test_acc"]) * 100.0
                    break

    float_acc_pct: float | None = None
    if metrics_path.is_file():
        meta = json.loads(metrics_path.read_text(encoding="utf-8"))
        ev = meta.get("evaluation") or {}
        if "float_acc" in ev:
            float_acc_pct = float(ev["float_acc"]) * 100.0
        else:
            for phase in meta.get("phases", []):
                if phase.get("name") == "float" and "best_test_acc" in phase:
                    float_acc_pct = float(phase["best_test_acc"]) * 100.0
                    break

    from datetime import datetime, timezone

    entry = {
        "id": model_id,
        "name": name,
        "framework": "PyTorch",
        "task": "图像分类",
        "params_count_m": 1.21,
        "input_shape": "1x28x28",
        "accuracy": float_acc_pct if float_acc_pct is not None else (acc or 0.0),
        "accuracy_fixed": acc or 0.0,
        "network": "A",
        "topology": "cnn_mnist_v1",
        "weights_dir": store_weights_path(weights_dir, repo_root=REPO),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    upsert_model(entry)
    snippet = weights_dir / "registry_snippet.json"
    snippet.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    print(f"Registered {model_id} -> {weights_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-dir", type=Path, required=True)
    parser.add_argument("--model-id", default="cnn-mnist-trained")
    parser.add_argument("--name", default="CNN MNIST Network A (trained)")
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
