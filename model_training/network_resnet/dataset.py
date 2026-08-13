"""CIFAR-10 dataloaders for ResNet-CIFAR (standard mean/std normalization)."""

from __future__ import annotations

from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]

CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD = (0.2470, 0.2435, 0.2616)


def cifar10_root() -> Path:
    return _REPO / "model_training" / "data" / "cifar10"


def download_cifar10(data_dir: Path | None = None) -> Path:
    root = (data_dir or cifar10_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    datasets.CIFAR10(root=str(root), train=True, download=True)
    datasets.CIFAR10(root=str(root), train=False, download=True)
    return root


def build_cifar10_loaders(
    *,
    batch_size: int = 128,
    num_workers: int | None = None,
    data_dir: Path | None = None,
    download: bool = True,
) -> tuple[DataLoader, DataLoader]:
    if num_workers is None:
        from model_training.device_utils import default_num_workers

        num_workers = default_num_workers()
    root = str((data_dir or cifar10_root()).resolve())
    if download:
        download_cifar10(data_dir)
    normalize = transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD)
    train_transform = transforms.Compose(
        [
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            normalize,
        ]
    )
    test_transform = transforms.Compose([transforms.ToTensor(), normalize])
    train_ds = datasets.CIFAR10(root=root, train=True, download=False, transform=train_transform)
    test_ds = datasets.CIFAR10(root=root, train=False, download=False, transform=test_transform)
    pin = torch.cuda.is_available()
    loader_kw: dict = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": pin,
    }
    if num_workers > 0:
        loader_kw["persistent_workers"] = True
        loader_kw["prefetch_factor"] = 2
    train_loader = DataLoader(train_ds, shuffle=True, **loader_kw)
    test_loader = DataLoader(test_ds, shuffle=False, **loader_kw)
    return train_loader, test_loader
