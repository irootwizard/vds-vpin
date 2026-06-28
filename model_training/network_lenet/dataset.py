"""CIFAR-10 dataloaders for LeNet-CIFAR — torchvision, cached under model_training/data/cifar10/.

Returns raw uint8 (3,32,32) tensors (PILToTensor); A_cifar_rgb normalization happens
inside the model preprocess, so the loaders stay adapter-agnostic and match the AHE
client path.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

_REPO = Path(__file__).resolve().parents[2]


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
    num_workers: int = 0,
    data_dir: Path | None = None,
    download: bool = True,
) -> tuple[DataLoader, DataLoader]:
    root = str((data_dir or cifar10_root()).resolve())
    if download:
        download_cifar10(data_dir)
    train_transform = transforms.Compose(
        [
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.PILToTensor(),
        ]
    )
    test_transform = transforms.PILToTensor()
    train_ds = datasets.CIFAR10(root=root, train=True, download=False, transform=train_transform)
    test_ds = datasets.CIFAR10(root=root, train=False, download=False, transform=test_transform)
    pin = torch.cuda.is_available()
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=pin
    )
    test_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=pin
    )
    return train_loader, test_loader
