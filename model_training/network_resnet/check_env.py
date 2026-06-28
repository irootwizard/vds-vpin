"""Check PyTorch / CUDA readiness for ResNet18-CIFAR training (no GPU required to run)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.device_utils import print_device_report, resolve_training_device


def main() -> int:
    dev, info = resolve_training_device("cuda")
    print_device_report(info)

    if dev.type != "cuda":
        print("[check_env] CUDA not ready - CPU fallback works for smoke tests; install GPU stack for training.")
        return 0

    import torch

    dev = torch.device("cuda:0")
    x = torch.randn(64, 3, 32, 32, device=dev)
    from model_training.network_resnet.resnet_cifar import resnet18

    model = resnet18().to(dev)
    with torch.inference_mode():
        y = model(x)
    torch.cuda.synchronize()
    print(f"[check_env] forward_ok shape={tuple(y.shape)} device={y.device}")
    print(f"[check_env] memory_allocated_MiB={torch.cuda.memory_allocated(0) / 1024 / 1024:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
