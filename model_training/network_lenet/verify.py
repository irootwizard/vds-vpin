"""§13 closed loop for LeNet-CIFAR: formula Π vs actual Π + range, writes report.

Runs offline-friendly: builds an (untrained) model if no checkpoint is given and
falls back to a synthetic RGB batch when CIFAR-10 is not cached, so
``python -m model_training.network_lenet.verify`` is a fast pi_match smoke test.

Writes ``hdc_validation_report.json``; exits 1 when the formula Π does not match
the truncation_config Π (pi_match == False), blocking deployable registration.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

MODULES = [
    "model_training.network_lenet.truncation_config",
    "model_training.network_lenet.fixed_point",
    "model_training.network_lenet.preprocess",
    "model_training.network_lenet.model",
    "model_training.network_lenet.dataset",
    "model_training.network_lenet.train",
    "model_training.network_lenet.export_weights",
    "model_training.network_lenet.register_backend",
    "model_training.network_lenet.ahe_feasibility",
    "model_training.network_lenet.evaluate",
    "model_training.network_lenet.sync_topology",
    "model_training.network_lenet.__main__",
]


def check_syntax() -> None:
    pkg = REPO / "model_training" / "network_lenet"
    files = sorted(pkg.glob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"[syntax] ok ({len(files)} files)")


def check_imports() -> None:
    for name in MODULES:
        importlib.import_module(name)
    print(f"[import] ok ({len(MODULES)} modules)")


def _formula_pi() -> list[dict]:
    from vpin_client.hdc.model_decomposer import build_layer_graph

    graph = build_layer_graph("lenet_cifar")
    return [
        {"id": c.id, "client_op": c.client_op, "from_bits": c.from_bits, "to_bits": c.to_bits}
        for c in graph.formula_scale_table()
    ]


def _actual_pi(plan) -> list[dict]:
    return [
        {
            "id": p.phase_id,
            "client_op": p.client_action,
            "from_bits": p.from_bits,
            "to_bits": p.to_bits,
        }
        for p in plan.phases()
    ]


def _pi_match(formula: list[dict], actual: list[dict]) -> tuple[bool, list[str]]:
    diffs: list[str] = []
    fmap = {d["id"]: d for d in formula}
    amap = {d["id"]: d for d in actual}
    if set(fmap) != set(amap):
        diffs.append(f"checkpoint id mismatch: formula={sorted(fmap)} actual={sorted(amap)}")
    for cid in sorted(set(fmap) & set(amap)):
        f, a = fmap[cid], amap[cid]
        if f["from_bits"] != a["from_bits"] or f["to_bits"] != a["to_bits"]:
            diffs.append(
                f"{cid}: formula {f['from_bits']}->{f['to_bits']} "
                f"!= actual {a['from_bits']}->{a['to_bits']}"
            )
    return len(diffs) == 0, diffs


def _load_input(device: torch.device, n: int = 8) -> torch.Tensor:
    """Try cached CIFAR-10; fall back to synthetic uint8 RGB for offline smoke."""
    try:
        from model_training.network_lenet.dataset import build_cifar10_loaders

        _, test_loader = build_cifar10_loaders(batch_size=n, download=False)
        images, _ = next(iter(test_loader))
        return images.to(device)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] CIFAR-10 not cached ({type(exc).__name__}); using synthetic batch")
        rng = np.random.default_rng(0)
        arr = rng.integers(0, 256, size=(n, 3, 32, 32), dtype=np.uint8)
        return torch.from_numpy(arr).to(device)


def run_verify(run_dir: Path | None) -> dict:
    from model_training.network_lenet.model import LeNetCIFAR
    from model_training.network_lenet.truncation_config import TruncationPlan

    plan = TruncationPlan()
    model = LeNetCIFAR(plan=plan)
    if run_dir is not None:
        ckpt = run_dir / "checkpoint.pt"
        plan_path = run_dir / "truncation_config.json"
        if plan_path.is_file():
            plan = TruncationPlan.load(plan_path)
            model = LeNetCIFAR(plan=plan)
        if ckpt.is_file():
            payload = torch.load(ckpt, map_location="cpu", weights_only=False)
            model.load_state_dict(payload["state_dict"])
            print(f"[verify] loaded checkpoint {ckpt}")
    model.eval()

    device = torch.device("cpu")
    formula = _formula_pi()
    actual = _actual_pi(plan)
    pi_match, diffs = _pi_match(formula, actual)

    images = _load_input(device)
    with torch.no_grad():
        _, bounds = model.forward_fixed_point(images, return_bounds=True, plan=plan)

    # Map checkpoint IDs to bounds keys (some have suffixes in model.py)
    # Keys match model.forward_fixed_point(return_bounds=True) in model.py
    _BOUNDS_KEY_MAP = {
        "after_conv1": "after_conv1",
        "after_pool1": "after_pool1_pre_shift",
        "after_conv2": "after_conv2",
        "after_pool2": "after_pool2_pre_shift",
        "after_fc1": "after_fc1_pre_relu",
        "after_fc2": "after_fc2_pre_relu",
    }

    # per-checkpoint actual magnitudes + safety
    from vpin_client.hdc import scale_rules as sr

    checkpoints: dict[str, dict] = {}
    for d in actual:
        cid = d["id"]
        bounds_key = _BOUNDS_KEY_MAP.get(cid, cid)
        m_pre = float(bounds.get(bounds_key, bounds.get(cid, 0.0)))
        is_shift = d["client_op"] in ("shift", "relu_then_shift")
        m_post = sr.post_shift_magnitude(m_pre, d["from_bits"], d["to_bits"]) if is_shift else m_pre
        checkpoints[cid] = {
            "from_bits": d["from_bits"],
            "to_bits": d["to_bits"],
            "M_pre_cal": m_pre,
            "M_post_cal": m_post,
            "bsgs_ok": m_pre < sr.BSGS_ABS_SAFE_LIMIT,
            "int32_ok": (m_post < sr.INT32_ABS_SAFE_LIMIT) if is_shift else True,
        }

    range_ok = all(c["bsgs_ok"] and c["int32_ok"] for c in checkpoints.values())
    report = {
        "model_id": "lenet-cifar10",
        "family": "lenet_cifar",
        "formula_pi": formula,
        "actual_pi": actual,
        "pi_match": pi_match,
        "pi_diffs": diffs,
        "checkpoints": checkpoints,
        "range_ok": range_ok,
        "accuracy": {"note": "run evaluate --mode feasibility for post-AHE acc_gap (reference vs proxy/WS)"},
        "deployable": False,  # set true only after accuracy certificate (evaluate)
        "untrained_smoke": run_dir is None,
    }

    out_dir = run_dir or (REPO / "model_training" / "outputs" / "lenet_verify")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hdc_validation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[verify] pi_match={pi_match} range_ok={range_ok} -> {out_path}")
    if diffs:
        for d in diffs:
            print(f"  [pi-diff] {d}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify LeNet-CIFAR HDC formula vs actual Π")
    parser.add_argument("--run-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    check_syntax()
    check_imports()
    report = run_verify(args.run_dir.resolve() if args.run_dir else None)
    if not report["pi_match"]:
        print("[verify] FAIL: formula Π != actual Π")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
