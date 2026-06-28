#!/usr/bin/env python3
"""Client-server AHE E2E smoke test (P0–P4).

Requires backend: ``python -m vpin_backend.main`` (default ws://127.0.0.1:8000).

Compares WebSocket AHE logits with homomorphic plaintext path (same weights as registry).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for sub in ("", "vpin-backend", "vpin-client"):
    p = REPO / sub if sub else REPO
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from model_training.network_a.evaluate import _numpy_homomorphic_plain
from model_training.network_a.truncation_config import TruncationPlan, plan_from_topology
from vpin_backend.crypto.ahe.codec import fixed_point_to_real
from vpin_backend.inference.homomorphic_network_a import load_network_a_weights
from vpin_backend.storage.registry import get_model
from vpin_client.data.preprocess import load_mnist_test
from vpin_client.hdc.data_adapters.cifar10_rgb import adapt_cifar_rgb
from vpin_client.models.weights_layout import is_lenet_cifar
from vpin_client.protocol.ws_ahe_client import run_ahe_session


def _plan_for_model(model_id: str, weights_dir: Path) -> TruncationPlan:
    """AHE WS uses topology.py shifts; plain-path parity must match."""
    topo_plan = plan_from_topology()
    cfg = weights_dir / "truncation_config.json"
    if cfg.is_file():
        loaded = TruncationPlan.load(cfg)
        if (
            loaded.shift_pool != topo_plan.shift_pool
            or loaded.shift_fc1 != topo_plan.shift_fc1
        ):
            import warnings

            warnings.warn(
                f"{cfg}: shift {loaded.shift_pool}/{loaded.shift_fc1} "
                f"!= topology {topo_plan.shift_pool}/{topo_plan.shift_fc1}; using topology",
                stacklevel=2,
            )
    return topo_plan


def _resolve_weights_dir(model_id: str) -> Path:
    from vpin_backend.config import get_settings
    from vpin_backend.models.weights_bundle import resolve_weights_dir

    entry = get_model(model_id)
    default = get_settings().cnn_networks_dir / "Pre_trained_model"
    if entry:
        return resolve_weights_dir(entry, default)
    if model_id == "lenet-cifar10":
        run = REPO / "model_training" / "outputs" / "20260623_185935"
        if run.is_dir():
            return run
    return default


def _resolve_network(model_id: str) -> str:
    entry = get_model(model_id) or {}
    net = entry.get("network")
    if net:
        return str(net)
    if model_id == "lenet-cifar10":
        return "lenet_cifar"
    return "A"


def _load_cifar10_test(index: int):
    try:
        from torchvision.datasets import CIFAR10
    except ImportError as exc:
        raise RuntimeError("torchvision required for --model lenet-cifar10") from exc

    data_root = REPO / "model_training" / "data"
    cifar_sub = data_root / "cifar10"
    root = str(cifar_sub) if cifar_sub.is_dir() else str(data_root)
    ds = CIFAR10(root=root, train=False, download=True)
    img, label = ds[index]
    arr = np.asarray(img)
    adapted = adapt_cifar_rgb(arr, label=int(label), index=index)
    fixed = adapted.fixed_int32[np.newaxis, ...]
    return fixed, int(label)


async def run_smoke(
    *,
    model_id: str,
    sample_index: int,
    backend: str,
) -> dict:
    network = _resolve_network(model_id)
    weights_dir = _resolve_weights_dir(model_id)

    if is_lenet_cifar(network):
        from vpin_backend.inference.homomorphic_network_lenet import (
            lenet_homomorphic_plain_logits,
            load_lenet_weights,
        )

        fixed, label = _load_cifar10_test(sample_index)
        weights = load_lenet_weights(weights_dir)
        plain_logits_i32 = lenet_homomorphic_plain_logits(fixed, weights)
        plain_logits = fixed_point_to_real(plain_logits_i32, 32).astype(np.float64)
        plain_pred = int(np.argmax(plain_logits_i32))
        index_key = "cifar_index"
    else:
        prep = load_mnist_test(sample_index)
        fixed = prep.fixed_int32
        label = prep.label
        weights = load_network_a_weights(weights_dir)
        plan = _plan_for_model(model_id, weights_dir)
        plain = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
        plain_logits = fixed_point_to_real(plain["after_fc2"][0], 16).astype(np.float64)
        plain_pred = int(np.argmax(plain_logits))
        index_key = "mnist_index"

    ahe = await run_ahe_session(
        backend,
        model_id,
        fixed,
        mnist_index=sample_index if index_key == "mnist_index" else None,
        label=label,
    )
    ahe_logits = np.array(ahe.logits, dtype=np.float64)
    logit_max_diff = float(np.max(np.abs(ahe_logits - plain_logits)))
    pred_match = plain_pred == ahe.prediction

    report = {
        "model_id": model_id,
        index_key: sample_index,
        "label": label,
        "plain_prediction": plain_pred,
        "ahe_prediction": ahe.prediction,
        "prediction_match": pred_match,
        "logit_max_diff": logit_max_diff,
        "num_pt_add": ahe.num_pt_add,
        "num_pt_mult": ahe.num_pt_mult,
        "timing_ms": ahe.timing.total_ms,
        "weights_dir": str(weights_dir.resolve()),
        "pass": pred_match and logit_max_diff == 0.0,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="AHE client-server E2E smoke test")
    parser.add_argument("--model", default="cnn-mnist-trained")
    parser.add_argument("--mnist-index", type=int, default=0, help="MNIST test index (Network A)")
    parser.add_argument("--cifar-index", type=int, default=0, help="CIFAR-10 test index (LeNet)")
    parser.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args()

    sample_index = args.cifar_index if args.model == "lenet-cifar10" else args.mnist_index

    try:
        report = asyncio.run(
            run_smoke(
                model_id=args.model,
                sample_index=sample_index,
                backend=args.backend,
            )
        )
    except Exception as exc:
        print(f"AHE smoke FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["pass"] else "FAIL"
        idx_key = "cifar_index" if args.model == "lenet-cifar10" else "mnist_index"
        print(
            f"[{status}] model={report['model_id']} {idx_key}={report[idx_key]} "
            f"plain={report['plain_prediction']} ahe={report['ahe_prediction']} "
            f"logit_max_diff={report['logit_max_diff']:.6f} "
            f"timing_ms={report['timing_ms']:.0f}"
        )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
