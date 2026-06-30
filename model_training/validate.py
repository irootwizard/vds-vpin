"""Validate LeNet5 and ResNet18 checkpoints on CIFAR-10 test set."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.new_lenet.model import LeNet5_CIFAR10
from model_training.new_resnet.model import ResNet18
from model_training.new_lenet.dataset import build_cifar10_loaders

CLASSES = ["airplane", "automobile", "bird", "cat", "deer",
           "dog", "frog", "horse", "ship", "truck"]

CHECKPOINTS = {
    "LeNet5":   REPO / "model_training/outputs/lenet_20260629_053826/checkpoint.pt",
    "ResNet18": REPO / "model_training/outputs/resnet18_20260629_054142/checkpoint.pt",
}


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device):
    model.eval()
    correct = total = 0
    per_class_correct = [0] * 10
    per_class_total   = [0] * 10
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            preds = model(images).argmax(dim=1)
            correct += (preds == labels).sum().item()
            total   += labels.size(0)
            for c in range(10):
                mask = labels == c
                per_class_total[c]   += mask.sum().item()
                per_class_correct[c] += (preds[mask] == c).sum().item()
    return correct / total, per_class_correct, per_class_total


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")

    _, test_loader = build_cifar10_loaders(batch_size=256, num_workers=2)

    models = {
        "LeNet5":   LeNet5_CIFAR10(),
        "ResNet18": ResNet18(),
    }

    for name, model in models.items():
        ckpt_path = CHECKPOINTS[name]
        ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["state_dict"])
        model.to(device)

        acc, cls_correct, cls_total = evaluate(model, test_loader, device)

        print(f"{'='*40}")
        print(f"  {name}")
        print(f"  Checkpoint: epoch={ckpt['epoch']}  saved_acc={ckpt['acc']:.4f}")
        print(f"  Overall test accuracy: {acc:.4f} ({acc*100:.2f}%)")
        print(f"  Per-class accuracy:")
        for i, cls in enumerate(CLASSES):
            cls_acc = cls_correct[i] / cls_total[i]
            print(f"    {cls:<12s}: {cls_acc:.4f} ({cls_correct[i]}/{cls_total[i]})")
        print()


if __name__ == "__main__":
    main()
