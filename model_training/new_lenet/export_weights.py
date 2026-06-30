"""Export trained LeNet5-CIFAR10 weights to .npy files for the AHE backend.

Weight layout for AHE (all float64):
  conv1_weight_6_3_5_5.npy   shape (6, 3, 5, 5)    — conv1 kernels (3-channel)
  conv1_bias_6.npy           shape (6,)
  conv2_weight_16_6_5_5.npy  shape (16, 6, 5, 5)   — conv2 kernels
  conv2_bias_16.npy          shape (16,)
  c3_weight_400_120.npy      shape (400, 120)       — c3 as FC, (in, out) convention
  c3_bias_120.npy            shape (120,)
  fc4_weight_120_84.npy      shape (120, 84)
  fc4_bias_84.npy            shape (84,)
  fc5_weight_84_10.npy       shape (84, 10)
  fc5_bias_10.npy            shape (10,)

Usage:
    python -m model_training.new_lenet.export_weights \\
        --checkpoint model_training/outputs/lenet_cifar10_<run_id>/checkpoint.pt \\
        --output-dir model_training/outputs/lenet_cifar10_<run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.new_lenet.model import LeNet5_CIFAR10
from model_training.new_lenet.truncation_config import (
    TRUNCATION_PLAN,
    BSGS_LIMIT,
    INT32_LIMIT,
    FIXED_POINT_BITS,
)


def export_weights(checkpoint: Path, output_dir: Path) -> dict:
    """Load checkpoint, export weights to output_dir, return shape summary."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state = ckpt.get("state_dict", ckpt)

    model = LeNet5_CIFAR10()
    model.load_state_dict(state)
    model.eval()

    def save(name: str, arr: np.ndarray):
        np.save(output_dir / name, arr.astype(np.float64))

    summary = {}

    # conv1 — Conv2d(3, 6, 5): weight (6, 3, 5, 5)
    w1 = model.c1.c1.weight.detach().numpy().astype(np.float64)
    b1 = model.c1.c1.bias.detach().numpy().astype(np.float64)
    save("conv1_weight_6_3_5_5.npy", w1)
    save("conv1_bias_6.npy", b1)
    summary["conv1_weight"] = list(w1.shape)
    summary["conv1_bias"]   = list(b1.shape)

    # conv2 — Conv2d(6, 16, 5): weight (16, 6, 5, 5)
    w2 = model.c2.c2.weight.detach().numpy().astype(np.float64)
    b2 = model.c2.c2.bias.detach().numpy().astype(np.float64)
    save("conv2_weight_16_6_5_5.npy", w2)
    save("conv2_bias_16.npy", b2)
    summary["conv2_weight"] = list(w2.shape)
    summary["conv2_bias"]   = list(b2.shape)

    # c3 — Conv2d(16, 120, 5) as FC(400→120)
    w3 = model.c3.c3.weight.detach().numpy().astype(np.float64)   # (120, 16, 5, 5)
    b3 = model.c3.c3.bias.detach().numpy().astype(np.float64)     # (120,)
    w3_fc = w3.reshape(120, 400).T                                  # (400, 120)
    save("c3_weight_400_120.npy", w3_fc)
    save("c3_bias_120.npy", b3)
    summary["c3_weight"] = list(w3_fc.shape)
    summary["c3_bias"]   = list(b3.shape)

    # fc4 — Linear(120, 84): weight (84, 120) → T → (120, 84)
    w4 = model.f4.f4.weight.detach().numpy().astype(np.float64)
    b4 = model.f4.f4.bias.detach().numpy().astype(np.float64)
    save("fc4_weight_120_84.npy", w4.T)
    save("fc4_bias_84.npy", b4)
    summary["fc4_weight"] = list(w4.T.shape)
    summary["fc4_bias"]   = list(b4.shape)

    # fc5 — Linear(84, 10): weight (10, 84) → T → (84, 10)
    w5 = model.f5.weight.detach().numpy().astype(np.float64)
    b5 = model.f5.bias.detach().numpy().astype(np.float64)
    save("fc5_weight_84_10.npy", w5.T)
    save("fc5_bias_10.npy", b5)
    summary["fc5_weight"] = list(w5.T.shape)
    summary["fc5_bias"]   = list(b5.shape)

    config = {
        "model": "lenet_cifar",
        "checkpoint": str(checkpoint),
        "fixed_point_bits": FIXED_POINT_BITS,
        "bsgs_limit": BSGS_LIMIT,
        "int32_limit": INT32_LIMIT,
        "truncation_plan": TRUNCATION_PLAN,
        "weight_shapes": summary,
    }
    (output_dir / "truncation_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )

    print(f"Exported LeNet-CIFAR10 weights to: {output_dir}")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Export LeNet5-CIFAR10 weights to .npy for AHE backend"
    )
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=None)
    args = p.parse_args(argv)
    out = args.output_dir or args.checkpoint.parent
    export_weights(args.checkpoint, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
