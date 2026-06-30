"""Train LeNet5-CIFAR10 on CIFAR-10 (32x32)."""

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

from model_training.new_lenet.dataset import build_cifar10_loaders
from model_training.new_lenet.model import LeNet5_CIFAR10


def _accuracy(model: nn.Module, loader, device: torch.device) -> float:
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            pred = model(images).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def train(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 1e-3,
    epochs: int = 50,
    weight_decay: float = 5e-4,
    num_workers: int = 4,
    output_root: Path | None = None,
) -> Path:
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    print(f"Device: {dev}")

    train_loader, test_loader = build_cifar10_loaders(batch_size=batch_size, num_workers=num_workers)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / f"lenet_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    model = LeNet5_CIFAR10().to(dev)
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_acc = 0.0
    metrics = {"run_id": run_id, "model": "LeNet5_CIFAR10", "input_size": 32, "epochs": []}

    for epoch in range(1, epochs + 1):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(dev), labels.to(dev)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
        scheduler.step()

        acc = _accuracy(model, test_loader, dev)
        metrics["epochs"].append({"epoch": epoch, "test_acc": round(acc, 4)})
        print(f"[epoch {epoch:3d}/{epochs}] test_acc={acc:.4f}")

        if acc > best_acc:
            best_acc = acc
            torch.save({"state_dict": model.state_dict(), "epoch": epoch, "acc": acc},
                       out_dir / "checkpoint.pt")

    metrics["best_test_acc"] = best_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nDone. best_test_acc={best_acc:.4f}  outputs -> {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Train LeNet5 on CIFAR-10")
    p.add_argument("--device",      default="cuda")
    p.add_argument("--batch-size",  type=int,   default=128)
    p.add_argument("--lr",          type=float, default=1e-3)
    p.add_argument("--epochs",      type=int,   default=50)
    p.add_argument("--num-workers", type=int,   default=4)
    p.add_argument("--output-root", type=Path,  default=None)
    args = p.parse_args(argv)
    train(
        device=args.device,
        batch_size=args.batch_size,
        lr=args.lr,
        epochs=args.epochs,
        num_workers=args.num_workers,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
