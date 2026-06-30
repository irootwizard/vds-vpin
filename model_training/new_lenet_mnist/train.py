"""Train LeNet5 on MNIST."""

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

from model_training.new_lenet_mnist.dataset import build_mnist_loaders
from model_training.new_lenet_mnist.model import LeNet5_MNIST


def _accuracy(model, loader, device):
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            correct += (model(images).argmax(dim=1) == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def train(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 1e-3,
    epochs: int = 20,
    num_workers: int = 4,
    output_root: Path | None = None,
) -> Path:
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    print(f"Device: {dev}")

    train_loader, test_loader = build_mnist_loaders(batch_size=batch_size, num_workers=num_workers)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / f"lenet_mnist_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    model = LeNet5_MNIST().to(dev)
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_acc = 0.0
    metrics = {"run_id": run_id, "model": "LeNet5_MNIST", "input_size": 32, "epochs": []}

    for epoch in range(1, epochs + 1):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(dev, non_blocking=True), labels.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
        scheduler.step()

        acc = _accuracy(model, test_loader, dev)
        lr_now = scheduler.get_last_lr()[0]
        metrics["epochs"].append({"epoch": epoch, "test_acc": round(acc, 4), "lr": lr_now})
        print(f"[epoch {epoch:2d}/{epochs}] test_acc={acc:.4f}  lr={lr_now:.6f}")

        if acc > best_acc:
            best_acc = acc
            torch.save({"state_dict": model.state_dict(), "epoch": epoch, "acc": acc},
                       out_dir / "checkpoint.pt")

    metrics["best_test_acc"] = best_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nDone. best_test_acc={best_acc:.4f}  outputs -> {out_dir}")
    return out_dir


def main(argv=None):
    p = argparse.ArgumentParser(description="Train LeNet5 on MNIST")
    p.add_argument("--device",      default="cuda")
    p.add_argument("--batch-size",  type=int,  default=128)
    p.add_argument("--lr",          type=float, default=1e-3)
    p.add_argument("--epochs",      type=int,  default=20)
    p.add_argument("--num-workers", type=int,  default=4)
    p.add_argument("--output-root", type=Path, default=None)
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
