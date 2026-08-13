"""Evaluate LeNet-CIFAR: float/fixed accuracy, bounds, HDC feasibility (§13 accuracy)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-client"))

from model_training.network_lenet.ahe_feasibility import (
    certificate_ahe_accuracy,
    certificate_float_fixed_diagnostic,
    compile_lenet_plan,
    scan_activation_bounds,
)
from model_training.network_lenet.dataset import build_cifar10_loaders
from model_training.network_lenet.model import LeNetCIFAR
from model_training.network_lenet.truncation_config import TruncationPlan, validate_activation_stats


def _load_model(run_dir: Path) -> tuple[LeNetCIFAR, TruncationPlan]:
    ckpt = run_dir / "checkpoint.pt"
    if not ckpt.is_file():
        raise FileNotFoundError(f"missing checkpoint: {ckpt}")
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    plan_path = run_dir / "truncation_config.json"
    plan = TruncationPlan.load(plan_path) if plan_path.is_file() else TruncationPlan()
    model = LeNetCIFAR(plan=plan)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, plan


def run_evaluation(run_dir: Path, *, modes: list[str]) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, plan = _load_model(run_dir)
    model = model.to(device)
    train_loader, test_loader = build_cifar10_loaders(batch_size=128)

    report: dict = {"run_dir": str(run_dir), "model_id": "lenet-cifar10", "modes": {}}
    want = lambda m: m in modes or "all" in modes  # noqa: E731

    if want("fixed"):
        diag = certificate_float_fixed_diagnostic(model, test_loader, device)
        report["modes"]["fixed"] = {
            "float": diag["float_acc"],
            "fixed": diag["fixed_acc"],
            "float_fixed_gap": diag["float_fixed_gap"],
            "diagnostic_only": True,
        }
        print(
            f"[fixed] float={diag['float_acc']:.4f} fixed={diag['fixed_acc']:.4f} "
            f"float_fixed_gap={diag['float_fixed_gap']:.4f} (diagnostic only)"
        )

    if want("bounds"):
        stats = scan_activation_bounds(model, train_loader, device, n=500)
        ok, errs = validate_activation_stats(stats, plan)
        report["modes"]["bounds"] = {"stats": stats.to_dict(), "pass": ok, "errors": errs}
        print(f"[bounds] pass={ok} " + (f"({errs})" if errs else ""))

    if want("feasibility"):
        deploy = compile_lenet_plan(model, train_loader, test_loader, device, plan=plan)
        deploy.save(run_dir / "homomorphic_deploy_plan.json")
        report["modes"]["feasibility"] = {
            "deployable": deploy.deployable,
            "range_ok": deploy.range_ok,
            "accuracy_ok": deploy.accuracy_ok,
            "accuracy": deploy.accuracy,
        }
        # Update validation report accuracy/deployable if present.
        vp = run_dir / "hdc_validation_report.json"
        if vp.is_file():
            data = json.loads(vp.read_text(encoding="utf-8"))
            data["accuracy"] = deploy.accuracy
            data["range_ok"] = deploy.range_ok
            data["deployable"] = bool(data.get("pi_match", False) and deploy.deployable)
            vp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(
            f"[feasibility] deployable={deploy.deployable} range_ok={deploy.range_ok} "
            f"acc_ok={deploy.accuracy_ok} reference={deploy.accuracy.get('reference_acc')} "
            f"ahe={deploy.accuracy.get('ahe_acc')} ahe_mode={deploy.accuracy.get('ahe_mode')}"
        )

    out_path = run_dir / "evaluation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate LeNet-CIFAR training run")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mode", default="all", help="fixed|bounds|feasibility|all")
    args = parser.parse_args(argv)
    modes = [args.mode]
    run_evaluation(args.run_dir.resolve(), modes=modes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
