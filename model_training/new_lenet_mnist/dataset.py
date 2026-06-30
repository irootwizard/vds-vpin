"""MNIST dataloaders — padded to 32x32 to match LeNet5 spatial flow."""

from __future__ import annotations
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]

MNIST_MEAN = (0.1307,)
MNIST_STD  = (0.3081,)


def mnist_root() -> Path:
    return _REPO / "model_training" / "data" / "mnist"


def build_mnist_loaders(
    *,
    batch_size: int = 128,
    num_workers: int = 4,
    data_dir: Path | None = None,
    download: bool = True,
) -> tuple[DataLoader, DataLoader]:
    root = str((data_dir or mnist_root()).resolve())
    normalize = transforms.Normalize(MNIST_MEAN, MNIST_STD)

    train_transform = transforms.Compose([
        transforms.Pad(2),                  # 28x28 → 32x32
        transforms.RandomCrop(32, padding=4),
        transforms.ToTensor(),
        normalize,
    ])
    test_transform = transforms.Compose([
        transforms.Pad(2),                  # 28x28 → 32x32
        transforms.ToTensor(),
        normalize,
    ])

    train_ds = datasets.MNIST(root=root, train=True,  download=download, transform=train_transform)
    test_ds  = datasets.MNIST(root=root, train=False, download=download, transform=test_transform)

    pin = torch.cuda.is_available()
    kw: dict = dict(batch_size=batch_size, num_workers=num_workers, pin_memory=pin)
    if num_workers > 0:
        kw["persistent_workers"] = True
        kw["prefetch_factor"] = 2

    return DataLoader(train_ds, shuffle=True, **kw), DataLoader(test_ds, shuffle=False, **kw)
