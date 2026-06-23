#!/usr/bin/env python3
"""Assess whether a Network A checkpoint is deployable on the current AHE stack.

Deployability criterion (default):
  - All truncate checkpoints within BSGS decrypt + int32 re-encrypt ranges
  - |Acc_float − Acc_fixed| < 0.001 on the official MNIST test set

Example:
  .\\.venv\\Scripts\\python.exe scripts\\check_ahe_feasibility.py \\
      --run-dir model_training/outputs/20260622_184254
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))

from model_training.network_a.ahe_feasibility import (
    DEFAULT_ACC_TOLERANCE,
    assess_ahe_feasibility,
)
from model_training.network_a.dataset import build_mnist_loaders
from model_training.network_a.evaluate import _load_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AHE homomorphic deployability check")
    parser.add_argument("--run-dir", type=Path, required=True, help="Training output directory")
    parser.add_argument("--cal-n", type=int, default=500, help="Calibration scan images (train split)")
    parser.add_argument("--margin-n", type=int, default=1000, help="Margin risk scan images")
    parser.add_argument("--acc-tolerance", type=float, default=DEFAULT_ACC_TOLERANCE)
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write report JSON (default: <run-dir>/ahe_feasibility_report.json)",
    )
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, plan = _load_model(run_dir)
    model = model.to(device)

    train_loader, test_loader = build_mnist_loaders(batch_size=256)

    report = assess_ahe_feasibility(
        model,
        train_loader,
        test_loader,
        device,
        plan=plan,
        cal_n=args.cal_n,
        margin_n=args.margin_n,
        acc_tolerance=args.acc_tolerance,
    )

    out_path = args.out or (run_dir / "ahe_feasibility_report.json")
    report.save(out_path)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("=== AHE Feasibility Assessment ===")
        print(f"run_dir: {run_dir}")
        print(f"deployable: {report.deployable}")
        print(f"range_ok: {report.range_ok}")
        print(f"accuracy_ok: {report.accuracy_ok}")
        acc = report.accuracy
        print(
            f"accuracy: float={acc['float_acc']:.4f} fixed={acc['fixed_acc']:.4f} "
            f"gap={acc['acc_gap']:.4f} (tolerance={acc['tolerance']})"
        )
        print(f"pred_mismatches: {acc['n_label_mismatches']} / {acc['n_samples']}")
        print("checkpoints:")
        for cp in report.checkpoints:
            print(
                f"  {cp['name']}: pre={cp['pre_shift_max']:.3e} (≈2^{cp['pre_shift_bits']}) "
                f"post={cp['post_shift_max']:.3e} bsgs={cp['bsgs_ok']} int32={cp['int32_reencrypt_ok']}"
            )
        mr = report.margin_risk
        print(
            f"margin_risk: mismatches={mr['n_float_fixed_mismatch']} "
            f"margin_below_bound={mr['n_margin_below_bound']} "
            f"perturb_bound={mr['logit_perturbation_bound']:.3e}"
        )
        if report.warnings:
            print("warnings:")
            for w in report.warnings:
                print(f"  - {w}")
        if report.errors:
            print("errors:")
            for e in report.errors:
                print(f"  - {e}")
        print(f"report: {out_path}")

    return 0 if report.deployable else 1


if __name__ == "__main__":
    raise SystemExit(main())
