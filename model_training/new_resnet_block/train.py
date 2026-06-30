"""Train ResNet18 for new_resnet_block.

Architecture and training procedure are identical to new_resnet.
Outputs go to model_training/outputs/resnet18_block_<run_id>/ to distinguish
from new_resnet runs.

Block linearization does NOT require retraining — run calibrate.py after training
(or point calibrate.py at an existing new_resnet checkpoint.pt).

Usage:
    python -m model_training.new_resnet_block.train [--epochs 120] [--device cuda]
"""

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

from model_training.new_resnet.dataset import build_cifar10_loaders
from model_training.new_resnet_block.model import ResNet18


def _accuracy(model: nn.Module, loader, device: torch.device, *, amp: bool) -> float:
    model.eval()
    correct = total = 0
    dtype = torch.float16 if amp and device.type == "cuda" else torch.float32
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            with torch.autocast(device_type=device.type, dtype=dtype,
                                enabled=amp and device.type == "cuda"):
                pred = model(images).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def train(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 0.1,
    epochs: int = 120,
    momentum: float = 0.9,
    weight_decay: float = 5e-4,
    milestone1: int = 60,
    milestone2: int = 90,
    num_workers: int = 4,
    amp: bool | None = None,
    output_root: Path | None = None,
) -> Path:
    dev     = torch.device(device if torch.cuda.is_available() else "cpu")
    use_amp = amp if amp is not None else dev.type == "cuda"
    print(f"Device: {dev}  AMP: {use_amp}")

    train_loader, test_loader = build_cifar10_loaders(
        batch_size=batch_size, num_workers=num_workers
    )

    run_id  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / f"resnet18_block_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    model = ResNet18().to(dev)
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(
        model.parameters(), lr=lr, momentum=momentum, weight_decay=weight_decay
    )
    scheduler = optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=[milestone1, milestone2], gamma=0.1
    )

    use_scaler = use_amp and dev.type == "cuda"
    scaler     = torch.amp.GradScaler("cuda", enabled=use_scaler)

    best_acc = 0.0
    metrics  = {
        "run_id": run_id, "model": "ResNet18Block_CIFAR",
        "input_size": 32, "epochs": [],
    }

    for epoch in range(1, epochs + 1):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(dev, non_blocking=True), labels.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev.type, dtype=torch.float16,
                                enabled=use_amp and dev.type == "cuda"):
                loss = criterion(model(images), labels)
            if use_scaler:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()
        scheduler.step()

        acc    = _accuracy(model, test_loader, dev, amp=use_amp)
        lr_now = scheduler.get_last_lr()[0]
        metrics["epochs"].append({"epoch": epoch, "test_acc": round(acc, 4), "lr": lr_now})
        print(f"[epoch {epoch:3d}/{epochs}] test_acc={acc:.4f}  lr={lr_now:.6f}")

        if acc > best_acc:
            best_acc = acc
            torch.save(
                {"state_dict": model.state_dict(), "epoch": epoch, "acc": acc},
                out_dir / "checkpoint.pt",
            )

    metrics["best_test_acc"] = best_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nDone. best_test_acc={best_acc:.4f}  outputs → {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Train ResNet18 for new_resnet_block")
    p.add_argument("--device",      default="cuda")
    p.add_argument("--batch-size",  type=int,   default=128)
    p.add_argument("--lr",          type=float, default=0.1)
    p.add_argument("--epochs",      type=int,   default=120)
    p.add_argument("--milestone1",  type=int,   default=60)
    p.add_argument("--milestone2",  type=int,   default=90)
    p.add_argument("--num-workers", type=int,   default=4)
    p.add_argument("--amp",         action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--output-root", type=Path,  default=None)
    args = p.parse_args(argv)
    train(
        device=args.device,
        batch_size=args.batch_size,
        lr=args.lr,
        epochs=args.epochs,
        milestone1=args.milestone1,
        milestone2=args.milestone2,
        num_workers=args.num_workers,
        amp=args.amp,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
