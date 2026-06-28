"""GPU training for LeNet-CIFAR (float warmup + optional fixed-point QAT)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.network_lenet.dataset import build_cifar10_loaders
from model_training.network_lenet.model import LeNetCIFAR
from model_training.network_lenet.truncation_config import (
    ActivationStats,
    TruncationPlan,
    validate_activation_stats,
)


def _accuracy(model: LeNetCIFAR, loader, device: torch.device, mode: str) -> float:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            if mode == "float":
                logits = model.forward_float(images)
            elif mode == "fixed":
                logits = model.forward_fixed_point(images, plan=model.plan)
            else:
                logits = model.forward_fixed_point_train(images)
            pred = logits.argmax(dim=1).to(labels.device)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def _calibrate(model: LeNetCIFAR, loader, device: torch.device, n: int = 200) -> ActivationStats:
    model.eval()
    stats = ActivationStats()
    seen = 0
    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True)
            stats.max_after_conv1 = max(stats.max_after_conv1, bounds.get("after_conv1_pre_relu", bounds.get("after_conv1", 0.0)))
            stats.max_after_pool1_pre_shift = max(stats.max_after_pool1_pre_shift, bounds.get("after_pool1_pre_shift", bounds.get("after_pool1", 0.0)))
            stats.max_after_conv2 = max(stats.max_after_conv2, bounds.get("after_conv2_pre_relu", bounds.get("after_conv2", 0.0)))
            stats.max_after_pool2_pre_shift = max(stats.max_after_pool2_pre_shift, bounds.get("after_pool2_pre_shift", bounds.get("after_pool2", 0.0)))
            stats.max_after_fc1_pre_relu = max(stats.max_after_fc1_pre_relu, bounds.get("after_fc1_pre_relu", bounds.get("after_fc1", 0.0)))
            stats.max_after_fc2_pre_relu = max(stats.max_after_fc2_pre_relu, bounds.get("after_fc2_pre_relu", bounds.get("after_fc2", 0.0)))
            seen += images.size(0)
    stats.n_samples = seen
    return stats


def train_network_lenet(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 1e-3,
    float_epochs: int = 40,
    fixed_epochs: int = 12,
    target_acc: float = 0.60,
    force_qat: bool = False,
    output_root: Path | None = None,
) -> Path:
    dev = torch.device(device if (torch.cuda.is_available() or device == "cpu") else "cpu")
    train_loader, test_loader = build_cifar10_loaders(batch_size=batch_size)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    model = LeNetCIFAR().to(dev)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.trainable_parameters(), lr=lr, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=float_epochs)

    metrics: dict = {"run_id": run_id, "model_id": "lenet-cifar10", "phases": []}

    best_float = 0.0
    for epoch in range(float_epochs):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(dev), labels.to(dev)
            optimizer.zero_grad()
            loss = criterion(model.forward_float(images), labels)
            loss.backward()
            optimizer.step()
        scheduler.step()
        acc = _accuracy(model, test_loader, dev, "float")
        best_float = max(best_float, acc)
        print(f"[float] epoch {epoch + 1}/{float_epochs} test_acc={acc:.4f}")
    metrics["phases"].append({"name": "float", "best_test_acc": best_float})

    plan = TruncationPlan(calibration=_calibrate(model, train_loader, dev))
    model.plan = plan
    plan.save(out_dir / "truncation_config.json")
    ok, errs = validate_activation_stats(plan.calibration, plan)
    metrics["truncation"] = plan.to_dict()
    metrics["range_ok"] = ok
    if not ok:
        print(f"[calibrate] range warnings: {errs}")

    float_ckpt = {"state_dict": model.state_dict(), "plan": plan.to_dict()}
    torch.save(float_ckpt, out_dir / "checkpoint_float.pt")
    torch.save(float_ckpt, out_dir / "checkpoint.pt")

    fixed_acc = _accuracy(model, test_loader, dev, "fixed")
    print(f"[calibrate] float_fixed_acc={fixed_acc:.4f}")
    metrics["float_fixed_acc"] = fixed_acc

    need_qat = force_qat or fixed_acc < target_acc
    if need_qat and fixed_epochs > 0:
        optimizer = optim.AdamW(model.trainable_parameters(), lr=lr * 0.1, weight_decay=5e-4)
        best_fixed = fixed_acc
        for epoch in range(fixed_epochs):
            model.train()
            for images, labels in train_loader:
                images, labels = images.to(dev), labels.to(dev)
                optimizer.zero_grad()
                loss = criterion(model.forward_fixed_point_train(images, plan=plan), labels)
                loss.backward()
                optimizer.step()
            acc = _accuracy(model, test_loader, dev, "fixed")
            print(f"[fixed] epoch {epoch + 1}/{fixed_epochs} test_acc={acc:.4f}")
            if acc > best_fixed:
                best_fixed = acc
                torch.save({"state_dict": model.state_dict(), "plan": plan.to_dict()}, out_dir / "checkpoint.pt")
        if best_fixed < fixed_acc:
            model.load_state_dict(torch.load(out_dir / "checkpoint_float.pt", weights_only=False)["state_dict"])
            torch.save(float_ckpt, out_dir / "checkpoint.pt")
            best_fixed = _accuracy(model, test_loader, dev, "fixed")
        metrics["phases"].append({"name": "fixed", "best_test_acc": best_fixed})
    else:
        metrics["phases"].append(
            {"name": "fixed", "best_test_acc": fixed_acc, "skipped": True, "force_qat": force_qat}
        )

    metrics["target_acc"] = target_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Done. outputs -> {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train LeNet-CIFAR on CIFAR-10 (HDC-aligned)")
    parser.add_argument("--dataset", default="cifar10")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--float-epochs", type=int, default=40)
    parser.add_argument("--fixed-epochs", type=int, default=12)
    parser.add_argument("--target-acc", type=float, default=0.60)
    parser.add_argument("--force-qat", action="store_true", help="always run fixed-point QAT phase")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.dataset.lower() != "cifar10":
        print(f"Error: network_lenet only supports --dataset cifar10, got {args.dataset!r}", file=sys.stderr)
        return 1
    train_network_lenet(
        device=args.device,
        batch_size=args.batch_size,
        lr=args.lr,
        float_epochs=args.float_epochs,
        fixed_epochs=args.fixed_epochs,
        target_acc=args.target_acc,
        force_qat=args.force_qat,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
