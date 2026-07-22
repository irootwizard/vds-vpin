"""Train SimpleCNN on LFW People (face classification)."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from model_training.simple_cnn_face.dataset import build_lfw_loaders
from model_training.simple_cnn_face.model import SimpleCNN


def train(args):
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Data
    train_loader, val_loader, num_classes, _ = build_lfw_loaders(
        image_size=args.image_size, batch_size=args.batch_size,
        num_workers=args.num_workers, top_k=args.top_k,
        min_samples=args.min_samples, download=args.download,
    )

    # Model
    model = SimpleCNN(num_classes=num_classes, dropout=args.dropout).to(device)

    # Loss, optimizer, scheduler
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Output dir
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = _REPO / "model_training" / "outputs" / f"simple_cnn_face_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    best_acc = 0.0
    metrics = []

    for epoch in range(1, args.epochs + 1):
        # Train
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * images.size(0)
            _, preds = outputs.max(1)
            train_correct += preds.eq(labels).sum().item()
            train_total += images.size(0)

        # Val
        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, preds = outputs.max(1)
                val_correct += preds.eq(labels).sum().item()
                val_total += images.size(0)

        scheduler.step()

        train_acc = 100.0 * train_correct / train_total
        val_acc = 100.0 * val_correct / val_total
        is_best = val_acc > best_acc
        if is_best:
            best_acc = val_acc

        print(f"Epoch {epoch:3d}/{args.epochs}  "
              f"train_loss={train_loss/train_total:.4f}  "
              f"train_acc={train_acc:.2f}%  val_acc={val_acc:.2f}%  "
              f"{'*BEST*' if is_best else ''}")

        metrics.append({"epoch": epoch, "train_acc": train_acc,
                        "val_acc": val_acc, "train_loss": train_loss / train_total})

        if is_best:
            torch.save({
                "state_dict": model.state_dict(),
                "epoch": epoch, "acc": val_acc, "num_classes": num_classes,
                "image_size": args.image_size,
            }, out_dir / "checkpoint.pt")

    # Save metrics
    (out_dir / "metrics.json").write_text(json.dumps({
        "best_val_acc": best_acc, "num_classes": num_classes,
        "image_size": args.image_size, "history": metrics,
    }, indent=2))

    print(f"\nBest val acc: {best_acc:.2f}%")
    print(f"Saved to: {out_dir}")
    return out_dir


def main(argv=None):
    p = argparse.ArgumentParser(description="Train SimpleCNN on LFW")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--dropout", type=float, default=0.3)
    p.add_argument("--image-size", type=int, default=64)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--min-samples", type=int, default=10)
    p.add_argument("--num-workers", type=int, default=2)
    p.add_argument("--device", default="cuda")
    p.add_argument("--download", action="store_true",
                   help="Download LFW dataset from torchvision")
    args = p.parse_args(argv)
    train(args)


if __name__ == "__main__":
    main()
