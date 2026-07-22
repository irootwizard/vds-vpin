"""Train ResNet18 on LFW People (face classification).

Usage:
    python -m model_training.resnet_face.train --download --epochs 50
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from model_training.simple_cnn_face.dataset import build_lfw_loaders
from model_training.new_resnet.model import ResNet18


def train(args):
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    train_loader, val_loader, num_classes, _ = build_lfw_loaders(
        image_size=args.image_size, batch_size=args.batch_size,
        num_workers=args.num_workers, top_k=args.top_k,
        min_samples=args.min_samples, download=args.download,
    )

    model = ResNet18()
    # Replace final FC for face identity count
    model.linear = nn.Linear(512, num_classes)
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=[30, 45], gamma=0.1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = _REPO / "model_training" / "outputs" / f"resnet_face_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    best_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * images.size(0)
            _, preds = model(images).max(1)
            train_correct += preds.eq(labels).sum().item()
            train_total += images.size(0)

        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                _, preds = model(images).max(1)
                val_correct += preds.eq(labels).sum().item()
                val_total += images.size(0)

        scheduler.step()
        val_acc = 100.0 * val_correct / val_total
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save({"state_dict": model.state_dict(), "epoch": epoch,
                        "acc": val_acc, "num_classes": num_classes},
                       out_dir / "checkpoint.pt")

        print(f"Epoch {epoch:3d}  train_loss={train_loss/train_total:.4f}  val_acc={val_acc:.2f}%")

    print(f"\nBest val acc: {best_acc:.2f}%  -> {out_dir}")
    return out_dir


def main(argv=None):
    p = argparse.ArgumentParser(description="Train ResNet18 on LFW")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=0.01)
    p.add_argument("--image-size", type=int, default=64)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--min-samples", type=int, default=10)
    p.add_argument("--num-workers", type=int, default=2)
    p.add_argument("--device", default="cuda")
    p.add_argument("--download", action="store_true")
    args = p.parse_args(argv)
    train(args)


if __name__ == "__main__":
    main()
