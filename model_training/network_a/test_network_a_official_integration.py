"""Integration tests: Network A wired to official MNIST + registry weights."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "vpin-backend") not in sys.path:
    sys.path.insert(0, str(REPO / "vpin-backend"))

from model_training.network_a.dataset import load_official_test_indices, mnist_data_root
from model_training.network_a.evaluate import (
    DEFAULT_RUN_DIR,
    _load_model,
    _numpy_homomorphic_plain,
    run_layerwise,
)
from model_training.network_a.truncation_config import plan_from_topology
from vpin_backend.inference.homomorphic_network_a import load_network_a_weights
from vpin_client.data.preprocess import load_mnist_test


@pytest.fixture(scope="module")
def registered_run_dir() -> Path:
    run_dir = DEFAULT_RUN_DIR
    assert run_dir.is_dir(), f"missing registered run dir: {run_dir}"
    for name in (
        "weight_fc1_64_16.npy",
        "bias_fc1_16.npy",
        "weight_fc2_16_10.npy",
        "bias_fc2_10.npy",
        "truncation_config.json",
    ):
        assert (run_dir / name).is_file(), f"missing weight artifact: {name}"
    return run_dir


def test_official_mnist_data_root_exists():
    root = mnist_data_root()
    assert root.is_dir()
    mnist_dir = root / "MNIST"
    assert mnist_dir.is_dir() or (root / "mnist").is_dir(), "official MNIST not downloaded under model_training/data"


def test_official_mnist_load_sample():
    samples = load_official_test_indices([0])
    assert len(samples) == 1
    img, label = samples[0]
    assert img.shape == (28, 28)
    assert img.dtype == np.uint8
    assert 0 <= label <= 9


def test_preprocess_matches_client_pipeline():
    prep = load_mnist_test(0)
    assert prep.fixed_int32.shape == (1, 1, 32, 32)
    assert prep.source == "official"
    assert prep.label is not None


def test_layerwise_torch_vs_homomorphic_plain(registered_run_dir: Path):
    report = run_layerwise(registered_run_dir, indices=[0, 1, 2, 3, 4])
    assert report["pass"] is True
    assert report["max_diff"] == 0.0
    for sample in report["samples"]:
        assert sample["pred_torch"] == sample["pred_numpy"]


def test_registered_weights_forward_shape(registered_run_dir: Path):
    model, plan = _load_model(registered_run_dir)
    weights = load_network_a_weights(registered_run_dir)
    prep = load_mnist_test(0)
    layers = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
    logits = layers["after_fc2"][0]
    assert logits.shape == (10,)
    assert np.all(logits >= 0)

    img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
    with torch.no_grad():
        torch_logits = model.forward_fixed_point(img, plan=plan)
    assert torch_logits.shape == (1, 10)
    np.testing.assert_array_equal(
        torch_logits[0].cpu().numpy().astype(np.int64),
        logits.astype(np.int64),
    )


def test_truncation_plan_matches_topology(registered_run_dir: Path):
    from model_training.network_a.truncation_config import load_plan_for_run

    loaded = load_plan_for_run(registered_run_dir)
    topo = plan_from_topology()
    assert loaded.shift_pool == topo.shift_pool
    assert loaded.shift_fc1 == topo.shift_fc1


def test_float_and_fixed_accuracy_on_official_mnist(registered_run_dir: Path):
    """Inference-path accuracy (not QAT training phase in metrics.json)."""
    model, plan = _load_model(registered_run_dir)
    model.eval()
    n = 256
    float_ok = fixed_ok = 0
    for i in range(n):
        prep = load_mnist_test(i)
        img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            pred_f = int(model.forward_float(img).argmax())
            pred_x = int(model.forward_fixed_point(img, plan=plan).argmax())
        if pred_f == prep.label:
            float_ok += 1
        if pred_x == prep.label:
            fixed_ok += 1
    float_acc = float_ok / n
    fixed_acc = fixed_ok / n
    assert float_acc >= 0.90, f"float acc too low: {float_acc:.4f}"
    assert fixed_acc >= 0.85, f"fixed acc too low: {fixed_acc:.4f}"
    assert float_acc - fixed_acc <= 0.10, f"float-fixed gap too large: {float_acc - fixed_acc:.4f}"
