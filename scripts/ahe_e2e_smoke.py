#!/usr/bin/env python3
"""Client-server AHE E2E smoke test (P0–P3).

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
    entry = get_model(model_id)
    if entry and entry.get("weights_dir"):
        return Path(entry["weights_dir"])
    from vpin_backend.config import get_settings

    return get_settings().cnn_networks_dir / "Pre_trained_model"


async def run_smoke(
    *,
    model_id: str,
    mnist_index: int,
    backend: str,
) -> dict:
    prep = load_mnist_test(mnist_index)
    weights_dir = _resolve_weights_dir(model_id)
    weights = load_network_a_weights(weights_dir)
    plan = _plan_for_model(model_id, weights_dir)

    plain = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
    plain_logits = fixed_point_to_real(plain["after_fc2"][0], 16).astype(np.float64)
    plain_pred = int(np.argmax(plain_logits))

    ahe = await run_ahe_session(
        backend,
        model_id,
        prep.fixed_int32,
        mnist_index=mnist_index,
        label=prep.label,
    )
    ahe_logits = np.array(ahe.logits, dtype=np.float64)
    logit_max_diff = float(np.max(np.abs(ahe_logits - plain_logits)))
    pred_match = plain_pred == ahe.prediction

    return {
        "model_id": model_id,
        "mnist_index": mnist_index,
        "label": prep.label,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="AHE client-server E2E smoke test")
    parser.add_argument("--model", default="cnn-mnist-trained")
    parser.add_argument("--mnist-index", type=int, default=0)
    parser.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args()

    try:
        report = asyncio.run(
            run_smoke(
                model_id=args.model,
                mnist_index=args.mnist_index,
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
        print(
            f"[{status}] model={report['model_id']} index={report['mnist_index']} "
            f"plain={report['plain_prediction']} ahe={report['ahe_prediction']} "
            f"logit_max_diff={report['logit_max_diff']:.6f} "
            f"timing_ms={report['timing_ms']:.0f}"
        )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
