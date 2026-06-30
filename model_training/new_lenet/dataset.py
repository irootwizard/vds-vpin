"""CIFAR-10 dataloaders for LeNet5 — standard 32x32 input."""

from __future__ import annotations
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]

CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD  = (0.2470, 0.2435, 0.2616)


def cifar10_root() -> Path:
    return _REPO / "model_training" / "data" / "cifar10"


def build_cifar10_loaders(
    *,
    batch_size: int = 128,
    num_workers: int = 4,
    data_dir: Path | None = None,
    download: bool = True,
) -> tuple[DataLoader, DataLoader]:
    root = str((data_dir or cifar10_root()).resolve())
    normalize = transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD)

    train_transform = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        normalize,
    ])
    test_transform = transforms.Compose([
        transforms.ToTensor(),
        normalize,
    ])

    train_ds = datasets.CIFAR10(root=root, train=True,  download=download, transform=train_transform)
    test_ds  = datasets.CIFAR10(root=root, train=False, download=download, transform=test_transform)

    pin = torch.cuda.is_available()
    kw: dict = dict(batch_size=batch_size, num_workers=num_workers, pin_memory=pin)
    if num_workers > 0:
        kw["persistent_workers"] = True
        kw["prefetch_factor"] = 2

    return DataLoader(train_ds, shuffle=True, **kw), DataLoader(test_ds, shuffle=False, **kw)
