"""CIFAR-10 sample loading for vPIN client preview."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def cifar10_bin_dir() -> Path:
    return _repo_root() / "model_training" / "data" / "cifar-10-batches-bin"


def _hwc_to_record(hwc: np.ndarray, label: int) -> bytes:
    if hwc.shape != (32, 32, 3):
        raise ValueError(f"expected HWC (32,32,3), got {hwc.shape}")
    r = hwc[:, :, 0].reshape(-1).astype(np.uint8)
    g = hwc[:, :, 1].reshape(-1).astype(np.uint8)
    b = hwc[:, :, 2].reshape(-1).astype(np.uint8)
    return bytes([int(label) & 0xFF]) + r.tobytes() + g.tobytes() + b.tobytes()


def ensure_cifar10_binary_batches() -> Path:
    """Export official CIFAR-10 binary batches for Rust lane (idempotent)."""
    out_dir = cifar10_bin_dir()
    if (out_dir / "test_batch.bin").is_file() and (out_dir / "data_batch_1.bin").is_file():
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    test_ds = _cifar10_dataset(train=False)
    train_ds = _cifar10_dataset(train=True)

    test_records: list[bytes] = []
    for i in range(len(test_ds)):
        img, label = test_ds[i]
        test_records.append(_hwc_to_record(np.asarray(img, dtype=np.uint8), int(label)))
    (out_dir / "test_batch.bin").write_bytes(b"".join(test_records))

    batch_size = 10_000
    for batch_no in range(1, 6):
        start = (batch_no - 1) * batch_size
        end = min(start + batch_size, len(train_ds))
        records: list[bytes] = []
        for i in range(start, end):
            img, label = train_ds[i]
            records.append(_hwc_to_record(np.asarray(img, dtype=np.uint8), int(label)))
        (out_dir / f"data_batch_{batch_no}.bin").write_bytes(b"".join(records))

    return out_dir


@lru_cache(maxsize=2)
def _cifar10_dataset(train: bool):
    try:
        from torchvision.datasets import CIFAR10
    except ImportError as exc:
        raise RuntimeError("torchvision required for CIFAR-10 loading") from exc

    data_root = _repo_root() / "model_training" / "data"
    cifar_sub = data_root / "cifar10"
    root = str(cifar_sub) if cifar_sub.is_dir() else str(data_root)
    return CIFAR10(root=root, train=train, download=True)


def fetch_cifar10_sample(index: int, *, train: bool = False) -> tuple[np.ndarray, int]:
    ensure_cifar10_binary_batches()
    limit = 50_000 if train else 10_000
    if index < 0 or index >= limit:
        raise IndexError(f"CIFAR-10 index must be 0..{limit - 1}, got {index}")
    ds = _cifar10_dataset(train)
    image, label = ds[index]
    arr = np.asarray(image, dtype=np.uint8)
    if arr.shape == (32, 32, 3):
        arr = np.transpose(arr, (2, 0, 1))
    return arr, int(label)
