"""Static checks for Network A training stack (no training)."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

MODULES = [
    "model_training.network_a.preprocess",
    "model_training.network_a.fixed_point",
    "model_training.network_a.truncation_config",
    "model_training.network_a.model",
    "model_training.network_a.dataset",
    "model_training.network_a.train",
    "model_training.network_a.export_weights",
    "model_training.network_a.register_backend",
    "model_training.network_a.evaluate",
    "model_training.network_a.sync_topology",
    "model_training.network_a.__main__",
]


def check_syntax() -> None:
    pkg = REPO / "model_training" / "network_a"
    for path in sorted(pkg.glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    print(f"[syntax] ok ({len(list(pkg.glob('*.py')))} files)")


def check_imports() -> None:
    for name in MODULES:
        importlib.import_module(name)
    print(f"[import] ok ({len(MODULES)} modules)")


def check_forward(device: torch.device) -> None:
    from model_training.network_a.dataset import build_mnist_loaders
    from model_training.network_a.model import NetworkA
    from model_training.network_a.truncation_config import plan_from_topology
    from vpin_backend.inference.homomorphic_network_a import NetworkAWeights

    plan = plan_from_topology()
    model = NetworkA(plan=plan).to(device)
    _, test_loader = build_mnist_loaders(batch_size=4)
    images, labels = next(iter(test_loader))
    images = images.to(device)

    with torch.no_grad():
        float_logits = model.forward_float(images)
        fixed_logits = model.forward_fixed_point(images, plan=plan)
        train_logits = model.forward_fixed_point_train(images, plan=plan)
        layers = model.forward_fixed_point_layers(images, plan=plan)
        _, bounds = model.forward_fixed_point(images, return_bounds=True, plan=plan)

    assert float_logits.shape == (4, 10)
    assert fixed_logits.shape == (4, 10)
    assert train_logits.shape == (4, 10)
    assert layers["after_pool"].shape == (4, 64)
    assert bounds["after_pool_pre_shift"] > 0
    print(f"[forward@{device}] ok shapes logits={tuple(float_logits.shape)}")

    from model_training.network_a.evaluate import _numpy_homomorphic_plain
    from vpin_client.data.preprocess import load_mnist_test

    prep = load_mnist_test(0)
    images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0).to(device)
    weights = NetworkAWeights(
        weight_fc1=model.fc1.weight.detach().cpu().numpy().T.astype(np.float64),
        bias_fc1=model.fc1.bias.detach().cpu().numpy().astype(np.float64),
        weight_fc2=model.fc2.weight.detach().cpu().numpy().T.astype(np.float64),
        bias_fc2=model.fc2.bias.detach().cpu().numpy().astype(np.float64),
    )
    np_layers = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
    torch_layers = model.forward_fixed_point_layers(images, plan=plan)
    diffs = {}
    for key in ("after_conv", "after_pool", "after_fc1", "after_fc2"):
        t = torch_layers[key].detach().cpu().numpy().astype(np.int64)
        n = np_layers[key].astype(np.int64)
        if key == "after_pool":
            t = t.reshape(1, -1)
        diffs[key] = int(np.max(np.abs(t - n)))
    print(f"[layerwise-smoke] max_diff={diffs}")
    if any(v != 0 for v in diffs.values()):
        raise RuntimeError(f"layerwise parity failed: {diffs}")


def check_data_source() -> None:
    from model_training.network_a.dataset import build_mnist_loaders, mnist_data_root

    root = mnist_data_root()
    root.mkdir(parents=True, exist_ok=True)
    _, test_loader = build_mnist_loaders(batch_size=4, data_dir=root)
    images, _labels = next(iter(test_loader))
    assert images.shape[0] == 4
    assert "cnn_networks" not in str(root.resolve())
    print(f"[data] MNIST ok -> {root}")


def main() -> int:
    check_syntax()
    check_imports()
    check_data_source()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    check_forward(device)
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
