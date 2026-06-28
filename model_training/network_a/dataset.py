"""MNIST dataloaders for Network A — official 60k/10k split only."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]
_CLIENT = _REPO / "vpin-client"
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))


def mnist_data_root() -> Path:
    return _REPO / "model_training" / "data"


def repo_data_dir() -> Path:
    return mnist_data_root()


def build_mnist_loaders(
    *,
    batch_size: int = 64,
    num_workers: int = 0,
    data_dir: Path | None = None,
) -> tuple[DataLoader, DataLoader]:
    root = data_dir or mnist_data_root()
    root.mkdir(parents=True, exist_ok=True)
    transform = transforms.PILToTensor()
    train_ds = datasets.MNIST(root=str(root), train=True, download=True, transform=transform)
    test_ds = datasets.MNIST(root=str(root), train=False, download=True, transform=transform)
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


def load_official_test_indices(indices: list[int]) -> list[tuple[np.ndarray, int]]:
    """Load raw uint8 (28,28) + label via vpin_client official pipeline."""
    from vpin_client.data.official import load_official_test

    out: list[tuple[np.ndarray, int]] = []
    for idx in indices:
        prep = load_official_test(idx)
        out.append((prep.raw_uint8, int(prep.label or -1)))
    return out
