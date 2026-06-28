"""Evaluation: fixed-point accuracy, layerwise parity, bounds, optional AHE WS."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = REPO / "model_training" / "outputs" / "20260622_184254"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

from model_training.network_a.dataset import build_mnist_loaders
from model_training.network_a.model import NetworkA
from model_training.network_a.truncation_config import (
    ActivationStats,
    TruncationPlan,
    load_plan_for_run,
    plan_from_topology,
    post_shift_magnitude,
    validate_activation_stats,
)
from vpin_backend.crypto.ahe.codec import real_to_fixed_point
from vpin_backend.inference.homomorphic_network_a import CONV_FILTER, NetworkAWeights, load_network_a_weights, my_conv2d
from vpin_client.crypto.ahe.activation import apply_client_action
from vpin_client.data.preprocess import load_mnist_test


def _load_model(run_dir: Path) -> tuple[NetworkA, TruncationPlan]:
    plan = load_plan_for_run(run_dir)
    model = NetworkA(plan=plan)
    ckpt = run_dir / "checkpoint.pt"
    if ckpt.is_file():
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        topo = plan_from_topology()
        if plan.shift_pool != topo.shift_pool or plan.shift_fc1 != topo.shift_fc1:
            print(
                f"[evaluate] truncation_config shift {plan.shift_pool}/{plan.shift_fc1}; "
                f"topology default {topo.shift_pool}/{topo.shift_fc1}"
            )
        elif isinstance(payload.get("plan"), dict) and not (run_dir / "truncation_config.json").is_file():
            p = payload["plan"]
            plan = TruncationPlan(
                shift_pool=int(p.get("shift_pool", plan.shift_pool)),
                shift_fc1=int(p.get("shift_fc1", plan.shift_fc1)),
            )
            model = NetworkA(plan=plan)
        model.load_state_dict(payload["state_dict"])
    else:
        model.fc1.weight.data = torch.from_numpy(np.load(run_dir / "weight_fc1_64_16.npy"))
        model.fc1.bias.data = torch.from_numpy(np.load(run_dir / "bias_fc1_16.npy"))
        model.fc2.weight.data = torch.from_numpy(np.load(run_dir / "weight_fc2_16_10.npy"))
        model.fc2.bias.data = torch.from_numpy(np.load(run_dir / "bias_fc2_10.npy"))
    model.eval()
    return model, plan


def _load_weights(run_dir: Path, model: NetworkA) -> NetworkAWeights:
    w1_path = run_dir / "weight_fc1_64_16.npy"
    if w1_path.is_file():
        return load_network_a_weights(run_dir)
    return NetworkAWeights(
        weight_fc1=model.fc1.weight.detach().numpy().T.astype(np.float64),
        bias_fc1=model.fc1.bias.detach().numpy().astype(np.float64),
        weight_fc2=model.fc2.weight.detach().numpy().T.astype(np.float64),
        bias_fc2=model.fc2.bias.detach().numpy().astype(np.float64),
    )


def _numpy_homomorphic_plain(
    fixed_32x32: np.ndarray,
    weights: NetworkAWeights,
    plan: TruncationPlan,
) -> dict[str, np.ndarray]:
    x = my_conv2d(
        fixed_32x32.astype(np.int64),
        CONV_FILTER,
        None,  # type: ignore[arg-type]
        padding_size=1,
        stride=1,
        ciphertext=False,
    )
    after_conv = apply_client_action(x.astype(np.int32), "relu")

    inv_fp = plan.pool_inv_fp
    h, w = after_conv.shape
    pooled = np.zeros((h // 4, w // 4), dtype=np.int64)
    for i in range(pooled.shape[0]):
        for j in range(pooled.shape[1]):
            pooled[i, j] = np.sum(after_conv[i * 4 : (i + 1) * 4, j * 4 : (j + 1) * 4]) * inv_fp
    after_pool = apply_client_action(pooled.astype(np.int32), "shift", shift_bits=plan.shift_pool)

    flat = after_pool.reshape(1, -1).astype(np.int64)
    w1 = real_to_fixed_point(weights.weight_fc1.astype(np.float64), bits=16).astype(np.int64)
    b1 = real_to_fixed_point(weights.bias_fc1.astype(np.float64), bits=16).astype(np.int64)
    x_fc1 = flat @ w1 + b1
    after_fc1 = apply_client_action(x_fc1[0], "relu_then_shift", shift_bits=plan.shift_fc1)

    w2 = real_to_fixed_point(weights.weight_fc2.astype(np.float64), bits=16).astype(np.int64)
    b2 = real_to_fixed_point(weights.bias_fc2.astype(np.float64), bits=16).astype(np.int64)
    x_fc2 = after_fc1.reshape(1, -1).astype(np.int64) @ w2 + b2
    after_fc2 = apply_client_action(x_fc2[0], "relu_only")

    return {
        "after_conv": after_conv,
        "after_pool": after_pool.reshape(1, -1),
        "after_fc1": after_fc1.reshape(1, -1),
        "after_fc2": after_fc2.reshape(1, -1),
    }


def _layerwise_max_diff(
    model: NetworkA,
    *,
    index: int,
    plan: TruncationPlan,
    weights: NetworkAWeights,
) -> dict[str, Any]:
    prep = load_mnist_test(index)
    img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
    device = next(model.parameters()).device
    with torch.no_grad():
        torch_layers = model.forward_fixed_point_layers(img.to(device), plan=plan)
    numpy_layers = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)

    layer_keys = ("after_conv", "after_pool", "after_fc1", "after_fc2")
    diffs: dict[str, float] = {}
    for key in layer_keys:
        a = torch_layers[key].detach().cpu().numpy().astype(np.int64)
        b = np.asarray(numpy_layers[key], dtype=np.int64)
        if key == "after_pool":
            a = a.reshape(1, -1)
        diffs[key] = float(np.max(np.abs(a - b)))

    logits_np = numpy_layers["after_fc2"][0].astype(np.int64)
    logits_torch = torch_layers["after_fc2"][0].detach().cpu().numpy().astype(np.int64)
    return {
        "index": index,
        "label": prep.label,
        "pred_torch": int(logits_torch.argmax()),
        "pred_numpy": int(logits_np.argmax()),
        "layer_max_diff": diffs,
        "max_diff": float(max(diffs.values())),
    }


def run_layerwise(
    run_dir: Path,
    *,
    indices: list[int] | None = None,
) -> dict[str, Any]:
    model, plan = _load_model(run_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    weights = _load_weights(run_dir, model)
    indices = indices if indices is not None else [0, 1, 2, 3, 4]
    samples = [_layerwise_max_diff(model, index=i, plan=plan, weights=weights) for i in indices]
    max_diff = max(s["max_diff"] for s in samples)
    return {
        "run_dir": str(run_dir.resolve()),
        "mode": "layerwise",
        "indices": indices,
        "samples": samples,
        "max_diff": max_diff,
        "pass": max_diff == 0.0,
    }


def run_fixed_accuracy(
    run_dir: Path,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    model, plan = _load_model(run_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    correct = 0
    total = 0
    for i in range(limit):
        prep = load_mnist_test(i)
        img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0).to(device)
        with torch.no_grad():
            logits = model.forward_fixed_point(img, plan=plan)
        pred = int(logits.argmax(dim=-1).item())
        if pred == prep.label:
            correct += 1
        total += 1
    acc = correct / total if total else 0.0
    return {
        "run_dir": str(run_dir.resolve()),
        "mode": "fixed_acc",
        "limit": limit,
        "fixed_acc": acc,
    }


def eval_fixed(model: NetworkA, loader, device: torch.device) -> float:
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            pred = model.forward_fixed_point(images, plan=model.plan).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def eval_bounds(
    model: NetworkA, loader, device: torch.device, n: int = 500
) -> tuple[dict[str, float], bool, str]:
    maxima: dict[str, float] = {}
    stats = ActivationStats()
    seen = 0
    plan = model.plan
    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True, plan=plan)
            for k, v in bounds.items():
                maxima[k] = max(maxima.get(k, 0.0), v)
            stats.max_after_pool_pre_shift = max(
                stats.max_after_pool_pre_shift, bounds.get("after_pool_pre_shift", 0.0)
            )
            stats.max_after_fc1_pre_relu = max(
                stats.max_after_fc1_pre_relu, bounds.get("after_fc1_pre_relu", 0.0)
            )
            stats.max_after_fc2_pre_relu = max(
                stats.max_after_fc2_pre_relu, bounds.get("after_fc2_pre_relu", 0.0)
            )
            seen += images.size(0)
    stats.n_samples = seen
    stats.max_post_pool_shift = post_shift_magnitude(
        stats.max_after_pool_pre_shift, plan.shift_pool
    )
    stats.max_post_fc1_shift = post_shift_magnitude(
        stats.max_after_fc1_pre_relu, plan.shift_fc1
    )
    ok, errors = validate_activation_stats(stats, plan)
    if not ok:
        return maxima, False, "; ".join(errors)
    return maxima, True, ""


def eval_layerwise(model: NetworkA, weights: NetworkAWeights, plan: TruncationPlan, n: int = 50) -> dict[str, int]:
    max_diff: dict[str, int] = {k: 0 for k in ("after_conv", "after_pool", "after_fc1", "after_fc2")}
    device = next(model.parameters()).device
    for i in range(n):
        prep = load_mnist_test(i)
        images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0).to(device)
        torch_layers = model.forward_fixed_point_layers(images, plan=plan)
        np_out = _numpy_homomorphic_plain(prep.fixed_int32[0, 0], weights, plan)
        for key in max_diff:
            t = torch_layers[key].detach().cpu().numpy().astype(np.int64)
            if key == "after_pool":
                t = t.reshape(1, -1)
            diff = int(np.max(np.abs(t - np_out[key].astype(np.int64))))
            max_diff[key] = max(max_diff[key], diff)
    return max_diff


async def eval_ahe_parity(
    *,
    model_id: str,
    model: NetworkA,
    limit: int,
    backend: str,
) -> dict[str, Any]:
    from vpin_client.protocol.ws_ahe_client import run_ahe_session

    device = next(model.parameters()).device
    fixed_correct = 0
    ahe_correct = 0
    mismatches = 0
    for i in range(limit):
        prep = load_mnist_test(i)
        images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0).to(device)
        label = prep.label
        assert label is not None
        with torch.no_grad():
            fixed_pred = int(model.forward_fixed_point(images, plan=model.plan).argmax(dim=-1).item())
        result = await run_ahe_session(
            backend,
            model_id,
            prep.fixed_int32,
            mnist_index=i,
            label=label,
            preprocess_ms=0.0,
        )
        ahe_pred = result.prediction
        if fixed_pred == label:
            fixed_correct += 1
        if ahe_pred == label:
            ahe_correct += 1
        if fixed_pred != ahe_pred:
            mismatches += 1

    fixed_acc = fixed_correct / limit
    ahe_acc = ahe_correct / limit
    return {
        "limit": limit,
        "fixed_acc": fixed_acc,
        "ahe_acc": ahe_acc,
        "acc_gap": abs(fixed_acc - ahe_acc),
        "pred_mismatches": mismatches,
    }


def run_evaluation(
    run_dir: Path,
    *,
    modes: list[str],
    model_id: str = "cnn-mnist-trained",
    ahe_limit: int = 50,
    backend: str = "ws://127.0.0.1:8000/api/v1/session/ws",
) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, plan = _load_model(run_dir)
    model = model.to(device)
    _, test_loader = build_mnist_loaders(batch_size=256)
    weights = _load_weights(run_dir, model)

    report: dict = {"run_dir": str(run_dir), "modes": {}}

    if "fixed" in modes or "all" in modes:
        acc = eval_fixed(model, test_loader, device)
        report["modes"]["fixed"] = {"test_acc": acc, "pass": acc >= 0.90}
        print(f"[fixed] test_acc={acc:.4f} pass={acc >= 0.90}")

    if "bounds" in modes or "all" in modes:
        maxima, bounds_ok, bounds_err = eval_bounds(model, test_loader, device)
        report["modes"]["bounds"] = {"maxima": maxima, "pass": bounds_ok, "error": bounds_err or None}
        print(f"[bounds] {maxima} pass={bounds_ok}" + (f" ({bounds_err})" if bounds_err else ""))

    if "layerwise" in modes or "all" in modes:
        diffs = eval_layerwise(model, weights, plan)
        ok = all(v == 0 for v in diffs.values())
        report["modes"]["layerwise"] = {"max_diff": diffs, "pass": ok}
        print(f"[layerwise] max_diff={diffs} pass={ok}")

    if "ahe" in modes or "all" in modes:
        ahe_report = asyncio.run(
            eval_ahe_parity(model_id=model_id, model=model, limit=ahe_limit, backend=backend)
        )
        ahe_report["pass"] = ahe_report["acc_gap"] <= 0.001 and ahe_report["pred_mismatches"] == 0
        report["modes"]["ahe"] = ahe_report
        print(
            f"[ahe] fixed={ahe_report['fixed_acc']:.4f} ahe={ahe_report['ahe_acc']:.4f} "
            f"gap={ahe_report['acc_gap']:.4f} mismatches={ahe_report['pred_mismatches']}"
        )

    if "feasibility" in modes or "all" in modes:
        from model_training.network_a.ahe_feasibility import assess_ahe_feasibility

        train_loader, test_loader = build_mnist_loaders(batch_size=256)
        feas = assess_ahe_feasibility(
            model, train_loader, test_loader, device, plan=plan, try_websocket=True
        )
        feas.save(run_dir / "ahe_feasibility_report.json")
        report["modes"]["feasibility"] = {
            "deployable": feas.deployable,
            "range_ok": feas.range_ok,
            "accuracy_ok": feas.accuracy_ok,
            "acc_gap": feas.accuracy["acc_gap"],
            "ahe_mode": feas.accuracy.get("ahe_mode"),
            "pass": feas.deployable,
        }
        print(
            f"[feasibility] deployable={feas.deployable} "
            f"reference={feas.accuracy['reference_acc']:.4f} ahe={feas.accuracy['ahe_acc']:.4f} "
            f"gap={feas.accuracy['acc_gap']:.4f} mode={feas.accuracy.get('ahe_mode')}"
        )

    out_path = run_dir / "evaluation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Network A training run")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--mode",
        default="all",
        help="fixed|layerwise|fixed_acc|bounds|ahe|feasibility|all",
    )
    parser.add_argument("--model-id", default="cnn-mnist-trained")
    parser.add_argument("--ahe-limit", type=int, default=50)
    parser.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    parser.add_argument("--limit", type=int, default=10, help="MNIST samples for fixed_acc quick mode")
    parser.add_argument("--indices", type=str, default="0,1,2,3,4", help="comma-separated test indices")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()

    if args.mode == "layerwise":
        indices = [int(x.strip()) for x in args.indices.split(",") if x.strip()]
        report = run_layerwise(run_dir, indices=indices)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            status = "PASS" if report["pass"] else "FAIL"
            print(f"[{status}] layerwise max_diff={report['max_diff']}")
        return 0 if report["pass"] else 1

    if args.mode == "fixed_acc":
        report = run_fixed_accuracy(run_dir, limit=args.limit)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"fixed_acc ({report['limit']} samples) = {report['fixed_acc']:.4f}")
        return 0

    modes = [args.mode] if args.mode != "all" else ["all"]
    run_evaluation(
        run_dir,
        modes=modes,
        model_id=args.model_id,
        ahe_limit=args.ahe_limit,
        backend=args.backend,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
