"""MNIST dataloaders for Network A — official 60k/10k split only."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]
_CLIENT = _REPO / "vpin-client"
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from vpin_client.data.official_mnist import download_official_mnist, official_mnist_root


def repo_data_dir() -> Path:
    return official_mnist_root()


def build_mnist_loaders(
    *,
    batch_size: int = 64,
    num_workers: int = 0,
    data_dir: Path | None = None,
) -> tuple[DataLoader, DataLoader]:
    root = str(download_official_mnist(data_dir))
    transform = transforms.PILToTensor()
    train_ds = datasets.MNIST(root=root, train=True, download=False, transform=transform)
    test_ds = datasets.MNIST(root=root, train=False, download=False, transform=transform)
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    return train_loader, test_loader
