"""MNIST sample loading shared by backend API and client."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np


@lru_cache(maxsize=1)
def _mnist_test_dataset():
    try:
        from torchvision.datasets import MNIST
    except ImportError as exc:
        raise RuntimeError("torchvision required for official MNIST loading") from exc

    repo = Path(__file__).resolve().parents[3]
    root = repo / "model_training" / "data"
    return MNIST(root=str(root), train=False, download=True)


def fetch_mnist_test_sample(index: int) -> tuple[np.ndarray, int]:
    if index < 0 or index > 9999:
        raise IndexError(f"MNIST index must be 0..9999, got {index}")
    ds = _mnist_test_dataset()
    image, label = ds[index]
    return np.asarray(image, dtype=np.uint8), int(label)


@lru_cache(maxsize=1)
def _mnist_train_dataset():
    try:
        from torchvision.datasets import MNIST
    except ImportError as exc:
        raise RuntimeError("torchvision required for official MNIST loading") from exc

    repo = Path(__file__).resolve().parents[3]
    root = repo / "model_training" / "data"
    return MNIST(root=str(root), train=True, download=True)


def fetch_mnist_train_sample(index: int) -> tuple[np.ndarray, int]:
    if index < 0 or index > 59999:
        raise IndexError(f"MNIST train index must be 0..59999, got {index}")
    ds = _mnist_train_dataset()
    image, label = ds[index]
    return np.asarray(image, dtype=np.uint8), int(label)
