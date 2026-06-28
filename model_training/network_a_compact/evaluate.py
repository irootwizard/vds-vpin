"""Evaluate Network A compact vs baseline Network A."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

from model_training.network_a.dataset import build_mnist_loaders
from model_training.network_a.evaluate import _load_model, _numpy_homomorphic_plain
from model_training.network_a.model import NetworkA
from model_training.network_a_compact.fixed_point import apply_client_action, check_reencrypt_range
from model_training.network_a_compact.model import NetworkACompact
from model_training.network_a_compact.weight_fusion import export_compact_bundle
from vpin_backend.inference.homomorphic_network_a import NetworkAWeights
from vpin_backend.inference.homomorphic_network_a_compact import (
    compact_plain_forward,
    load_compact_weights,
)


def _accuracy(model: NetworkACompact, loader, device: torch.device) -> float:
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            pred = model.forward_fixed_point(images).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def _max_diff(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.max(np.abs(a.astype(np.int64) - b.astype(np.int64))))


def evaluate_compact(
    run_dir: Path,
    *,
    n_layerwise: int = 20,
    n_acc: int = 1000,
    device: str = "cpu",
) -> dict:
    dev = torch.device(device)
    base_model, plan = _load_model(run_dir)
    base_model = base_model.to(dev)

    _, test_loader = build_mnist_loaders(batch_size=256)
    weights = NetworkAWeights(
        weight_fc1=np.load(run_dir / "weight_fc1_64_16.npy"),
        bias_fc1=np.load(run_dir / "bias_fc1_16.npy"),
        weight_fc2=np.load(run_dir / "weight_fc2_16_10.npy"),
        bias_fc2=np.load(run_dir / "bias_fc2_10.npy"),
    )

    compact_dir = run_dir / "compact_weights"
    if not (compact_dir / "weight_fc1_64_16.npy").is_file():
        bundle = export_compact_bundle(
            weight_fc1=weights.weight_fc1,
            bias_fc1=weights.bias_fc1,
            weight_fc2=weights.weight_fc2,
            bias_fc2=weights.bias_fc2,
        )
        compact_dir.mkdir(parents=True, exist_ok=True)
        for k, v in bundle.items():
            np.save(compact_dir / k, v)

    cw = load_compact_weights(compact_dir)
    report: dict = {"run_dir": str(run_dir), "variants": {}}

    for mode in ("int32", "int64"):
        compact = NetworkACompact.from_network_a(base_model, quant_mode=mode)
        compact = compact.to(dev)
        acc = _accuracy(compact, test_loader, dev)
        layer_diff: dict[str, int] = {}
        parity_ok = 0
        from vpin_client.data.preprocess import load_mnist_test

        for i in range(n_layerwise):
            prep = load_mnist_test(i)
            ref = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
            got = compact_plain_forward(prep.fixed_int32[0, 0], cw, quant_mode=mode)
            for key in ("after_conv", "after_fc2"):
                if key in ref and key in got:
                    layer_diff[key] = max(layer_diff.get(key, 0), _max_diff(ref[key], got[key]))
            if int(np.argmax(ref["after_fc2"])) == int(np.argmax(got["after_fc2"])):
                parity_ok += 1

        report["variants"][mode] = {
            "accuracy_n": n_acc if n_acc else "full_loader",
            "test_accuracy": acc,
            "client_rounds": 3,
            "layer_max_diff": layer_diff,
            "argmax_match_vs_baseline_plain": f"{parity_ok}/{n_layerwise}",
        }

    base_acc = 0.0
    correct = total = 0
    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(dev)
            labels = labels.to(dev)
            pred = base_model.forward_fixed_point(images, plan=plan).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    base_acc = correct / max(total, 1)
    report["baseline_network_a"] = {"test_accuracy": base_acc, "client_rounds": 4}

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate network_a_compact int32/int64")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--layerwise-n", type=int, default=20)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = evaluate_compact(args.run_dir.resolve(), n_layerwise=args.layerwise_n)
    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
