"""LFW People dataset loader with top-K identity filtering."""

import torch
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
from torchvision.datasets import LFWPeople
from pathlib import Path
from collections import Counter
import sys

_REPO = Path(__file__).resolve().parents[2]
DATA_DIR = _REPO / "model_training" / "data" / "lfw"

# ImageNet normalization (standard for face models)
FACE_MEAN = (0.485, 0.456, 0.406)
FACE_STD = (0.229, 0.224, 0.225)


def _top_k_people(dataset: LFWPeople, k: int = 50, min_samples: int = 10):
    """Filter dataset to top-K identities with at least min_samples images."""
    targets = [dataset.targets[i].item() if hasattr(dataset.targets[i], 'item')
               else int(dataset.targets[i]) for i in range(len(dataset))]
    counts = Counter(targets)
    top_ids = [pid for pid, cnt in counts.most_common(k) if cnt >= min_samples]
    indices = [i for i, t in enumerate(targets) if t in top_ids]
    # Remap targets to 0..K-1
    id_map = {old: new for new, old in enumerate(sorted(top_ids))}
    return indices, id_map, top_ids


def build_lfw_loaders(
    image_size: int = 64,
    batch_size: int = 64,
    num_workers: int = 2,
    top_k: int = 50,
    min_samples: int = 10,
    download: bool = False,
):
    """Build train/val DataLoaders for LFW People.

    Returns (train_loader, val_loader, num_classes, id_map).
    """
    train_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(FACE_MEAN, FACE_STD),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(FACE_MEAN, FACE_STD),
    ])

    root = str(DATA_DIR.resolve())
    full_ds = LFWPeople(root=root, split="10fold", image_set="funneled",
                        transform=None, download=download)

    indices, id_map, top_ids = _top_k_people(full_ds, k=top_k, min_samples=min_samples)
    num_classes = len(top_ids)
    if num_classes == 0:
        raise RuntimeError(
            f"No identities with >= {min_samples} samples in LFW. "
            f"Try lower min_samples or download the dataset first."
        )

    # Train/val split: 80/20 per identity
    train_idx, val_idx = [], []
    targets = [full_ds.targets[i].item() if hasattr(full_ds.targets[i], 'item')
               else int(full_ds.targets[i]) for i in range(len(full_ds))]
    for pid in sorted(top_ids):
        pid_indices = [i for i in indices if targets[i] == pid]
        split = int(len(pid_indices) * 0.8)
        train_idx.extend(pid_indices[:split])
        val_idx.extend(pid_indices[split:])

    train_ds = _RemappedLFW(full_ds, train_idx, id_map, train_tf)
    val_ds = _RemappedLFW(full_ds, val_idx, id_map, val_tf)

    kw = dict(batch_size=batch_size, num_workers=num_workers,
              pin_memory=torch.cuda.is_available())
    train_loader = DataLoader(train_ds, shuffle=True, **kw)
    val_loader = DataLoader(val_ds, shuffle=False, **kw)

    print(f"LFW: {num_classes} classes, {len(train_idx)} train, {len(val_idx)} val")
    return train_loader, val_loader, num_classes, id_map


class _RemappedLFW(torch.utils.data.Dataset):
    """Wraps LFWPeople with remapped labels 0..K-1 and a transform."""
    def __init__(self, base_ds, indices, id_map, transform):
        self.base_ds = base_ds
        self.indices = indices
        self.id_map = id_map
        self.transform = transform

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        img, orig_label = self.base_ds[self.indices[idx]]
        return self.transform(img), self.id_map[orig_label]
