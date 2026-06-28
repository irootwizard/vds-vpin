"""Training for ResNet18-CIFAR on CIFAR-10 (CUDA-ready, CPU fallback)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.device_utils import (
    amp_dtype,
    default_num_workers,
    print_device_report,
    resolve_training_device,
    set_seed,
)
from model_training.network_resnet.dataset import build_cifar10_loaders
from model_training.network_resnet.resnet_cifar import ResNet18CIFAR, resnet18


def _to_device(batch: torch.Tensor, device: torch.device, *, non_blocking: bool) -> torch.Tensor:
    return batch.to(device, non_blocking=non_blocking)


def _accuracy(
    model: nn.Module,
    loader,
    device: torch.device,
    *,
    amp: bool,
    non_blocking: bool,
) -> float:
    model.eval()
    correct = 0
    total = 0
    dtype = amp_dtype(device) if amp and device.type == "cuda" else torch.float32
    with torch.inference_mode():
        for images, labels in loader:
            images = _to_device(images, device, non_blocking=non_blocking)
            labels = _to_device(labels, device, non_blocking=non_blocking)
            with torch.autocast(device_type=device.type, dtype=dtype, enabled=amp and device.type == "cuda"):
                pred = model(images).argmax(dim=1)
            correct += (pred == labels).sum().item()
            total += labels.size(0)
    return correct / max(total, 1)


def train_resnet18_cifar(
    *,
    device: str = "cuda",
    batch_size: int = 128,
    lr: float = 0.1,
    epochs: int = 120,
    momentum: float = 0.9,
    weight_decay: float = 5e-4,
    milestone1: int = 60,
    milestone2: int = 90,
    num_workers: int | None = None,
    amp: bool | None = None,
    seed: int = 42,
    compile_model: bool = False,
    output_root: Path | None = None,
) -> Path:
    set_seed(seed)
    dev, dev_info = resolve_training_device(device)
    print_device_report(dev_info)

    use_amp = amp if amp is not None else dev.type == "cuda"
    non_blocking = dev.type == "cuda"
    workers = default_num_workers() if num_workers is None else num_workers
    train_loader, test_loader = build_cifar10_loaders(batch_size=batch_size, num_workers=workers)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (output_root or REPO / "model_training" / "outputs") / f"resnet18_cifar_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    model = resnet18().to(dev)
    if compile_model and dev.type == "cuda" and hasattr(torch, "compile"):
        model = torch.compile(model)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=momentum, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=[milestone1, milestone2], gamma=0.1)

    dtype = amp_dtype(dev)
    use_scaler = use_amp and dev.type == "cuda" and dtype == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=use_scaler)

    metrics: dict = {
        "run_id": run_id,
        "model_id": ResNet18CIFAR.MODEL_ID,
        "network_family": ResNet18CIFAR.NETWORK_FAMILY,
        "dataset": "cifar10",
        "device": str(dev),
        "amp": use_amp,
        "amp_dtype": str(dtype) if use_amp and dev.type == "cuda" else "float32",
        "batch_size": batch_size,
        "num_workers": workers,
        "seed": seed,
        "device_info": dev_info,
        "epochs": [],
        "best_test_acc": 0.0,
    }

    best_acc = 0.0
    for epoch in range(epochs):
        model.train()
        for images, labels in train_loader:
            images = _to_device(images, dev, non_blocking=non_blocking)
            labels = _to_device(labels, dev, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev.type, dtype=dtype, enabled=use_amp and dev.type == "cuda"):
                loss = criterion(model(images), labels)
            if use_scaler:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()
        scheduler.step()
        acc = _accuracy(model, test_loader, dev, amp=use_amp, non_blocking=non_blocking)
        metrics["epochs"].append({"epoch": epoch + 1, "test_acc": acc, "lr": scheduler.get_last_lr()[0]})
        print(f"[train] epoch {epoch + 1}/{epochs} test_acc={acc:.4f} lr={scheduler.get_last_lr()[0]:.6f}")
        if acc > best_acc:
            best_acc = acc
            ckpt = {
                "state_dict": model.state_dict(),
                "model_id": ResNet18CIFAR.MODEL_ID,
                "network_family": ResNet18CIFAR.NETWORK_FAMILY,
                "epoch": epoch + 1,
                "test_acc": acc,
                "device": str(dev),
                "amp": use_amp,
            }
            torch.save(ckpt, out_dir / "checkpoint.pt")

    metrics["best_test_acc"] = best_acc
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Done. best_test_acc={best_acc:.4f} outputs -> {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train ResNet18 on CIFAR-10")
    parser.add_argument("--dataset", default="cifar10")
    parser.add_argument("--device", default="cuda", help="cuda | cuda:0 | cpu")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--milestone1", type=int, default=60)
    parser.add_argument("--milestone2", type=int, default=90)
    parser.add_argument("--num-workers", type=int, default=None, help="DataLoader workers (default: auto)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=None, help="mixed precision (default: on for CUDA)")
    parser.add_argument("--compile", action="store_true", help="torch.compile (CUDA only, optional)")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.dataset.lower() != "cifar10":
        print(f"Error: network_resnet only supports --dataset cifar10, got {args.dataset!r}", file=sys.stderr)
        return 1
    train_resnet18_cifar(
        device=args.device,
        batch_size=args.batch_size,
        lr=args.lr,
        epochs=args.epochs,
        milestone1=args.milestone1,
        milestone2=args.milestone2,
        num_workers=args.num_workers,
        amp=args.amp,
        seed=args.seed,
        compile_model=args.compile,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
