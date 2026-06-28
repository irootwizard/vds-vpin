"""GPU training for Network A MNIST (float warmup + fixed-point QAT)."""

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

from model_training.network_b.dataset import build_mnist_loaders
from model_training.network_b.model import NetworkB
from model_training.network_b.sync_topology import sync_topology_if_needed
from model_training.network_b.truncation_config import (
    ActivationStats,
    batch_calibrate_shifts,
    validate_activation_stats,
)


def _accuracy(model: NetworkB, loader, device: torch.device, mode: str) -> float:
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
            pred = logits.argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def _calibrate_plan(model: NetworkB, loader, device: torch.device, n: int = 200):
    model.eval()
    max_pool = 0.0
    max_fc1 = 0.0
    max_fc2 = 0.0
    seen = 0
    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True)
            max_pool = max(max_pool, bounds["after_pool_pre_shift"])
            max_fc1 = max(max_fc1, bounds["after_fc1_pre_relu"])
            max_fc2 = max(max_fc2, bounds.get("after_fc2_pre_relu", 0.0))
            seen += images.size(0)
    stats = ActivationStats(
        n_samples=seen,
        max_after_pool_pre_shift=max_pool,
        max_after_fc1_pre_relu=max_fc1,
        max_after_fc2_pre_relu=max_fc2,
        max_post_pool_shift=0.0,
        max_post_fc1_shift=0.0,
    )
    plan = batch_calibrate_shifts(
        max_after_pool=max_pool,
        max_after_fc1_pre_relu=max_fc1,
        max_after_fc2_pre_relu=max_fc2,
        n_samples=seen,
    )
    ok, errs = validate_activation_stats(plan.calibration or stats, plan)
    if not ok:
        print(f"[calibrate] bounds warnings: {errs}")
    return plan


def train_network_b(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 1e-3,
    float_epochs: int = 30,
    fixed_epochs: int = 20,
    patience: int = 3,
    target_acc: float = 0.90,
    output_root: Path | None = None,
) -> Path:
    dev = torch.device(device if torch.cuda.is_available() or device == "cpu" else "cpu")
    train_loader, test_loader = build_mnist_loaders(batch_size=batch_size)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    model = NetworkB().to(dev)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.trainable_parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=float_epochs)

    metrics: dict = {"run_id": run_id, "phases": []}

    # Phase A: float warmup
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

    # Calibrate truncation
    plan = _calibrate_plan(model, train_loader, dev)
    model.plan = plan
    plan.save(out_dir / "truncation_config.json")
    synced = sync_topology_if_needed(plan)
    metrics["truncation"] = plan.to_dict()
    metrics["topology_synced"] = synced
    print(f"[calibrate] shift_pool={plan.shift_pool} shift_fc1={plan.shift_fc1} synced={synced}")

    # Seed checkpoints from float warmup.
    float_ckpt = {"state_dict": model.state_dict(), "plan": plan.to_dict()}
    torch.save(float_ckpt, out_dir / "checkpoint_float.pt")
    torch.save(float_ckpt, out_dir / "checkpoint.pt")

    float_fixed_acc = _accuracy(model, test_loader, dev, "fixed")
    print(f"[calibrate] float_fixed_acc={float_fixed_acc:.4f}")
    metrics["float_fixed_acc"] = float_fixed_acc

    if float_fixed_acc >= target_acc:
        print(f"[fixed] skip QAT: fixed acc already>={target_acc}")
        metrics["phases"].append({"name": "fixed", "best_test_acc": float_fixed_acc, "skipped": True})
        metrics["target_acc"] = target_acc
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Done. outputs -> {out_dir}")
        return out_dir

    # Phase B: fixed-point QAT (only if float weights insufficient for fixed inference)
    optimizer = optim.AdamW(model.trainable_parameters(), lr=lr * 0.05, weight_decay=1e-4)
    best_fixed = float_fixed_acc
    stale = 0
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
            stale = 0
            if acc >= best_float * 0.5:
                torch.save(
                    {"state_dict": model.state_dict(), "plan": plan.to_dict()},
                    out_dir / "checkpoint.pt",
                )
        else:
            stale += 1
        if acc >= target_acc and stale >= patience:
            print(f"[fixed] early stop: acc>={target_acc}")
            break

    if best_fixed < target_acc:
        print(f"[fixed] QAT did not reach target; restore float checkpoint (best_fixed={best_fixed:.4f})")
        model.load_state_dict(torch.load(out_dir / "checkpoint_float.pt", weights_only=False)["state_dict"])
        torch.save(float_ckpt, out_dir / "checkpoint.pt")
        best_fixed = _accuracy(model, test_loader, dev, "fixed")

    metrics["phases"].append({"name": "fixed", "best_test_acc": best_fixed})
    metrics["target_acc"] = target_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Done. outputs -> {out_dir} best_fixed={best_fixed:.4f}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train Network A on MNIST (AHE-aligned)")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--float-epochs", type=int, default=30)
    parser.add_argument("--fixed-epochs", type=int, default=20)
    parser.add_argument("--target-acc", type=float, default=0.90)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    train_network_b(
        device=args.device,
        batch_size=args.batch_size,
        lr=args.lr,
        float_epochs=args.float_epochs,
        fixed_epochs=args.fixed_epochs,
        target_acc=args.target_acc,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
