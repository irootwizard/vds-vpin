#!/usr/bin/env python3
"""Restore Network A Pre_trained_model/*.npy from full_weights.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
JSON_PATH = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "full_weights.json"
OUT_DIR = REPO / "src" / "cnn_networks" / "Pre_trained_model"

SEGMENTS = {
    "conv": 9,
    "fc1_weights": 64 * 16,
    "fc1_bias": 16,
    "fc2_weights": 16 * 10,
    "fc2_bias": 10,
}


def _to_signed_int32(v: int) -> int:
    if v >= (1 << 31):
        v -= 1 << 32
    return int(v)


def _fp_to_float(v: int) -> float:
    return _to_signed_int32(v) / (2**16)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=JSON_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    payload = json.loads(args.json.read_text(encoding="utf-8"))
    flat = [int(x) for x in payload["w_star_flat"]]
    if len(flat) != 1219:
        raise SystemExit(f"expected 1219 weights, got {len(flat)}")

    offset = 0
    conv = flat[offset : offset + SEGMENTS["conv"]]
    offset += SEGMENTS["conv"]
    w1 = flat[offset : offset + SEGMENTS["fc1_weights"]]
    offset += SEGMENTS["fc1_weights"]
    b1 = flat[offset : offset + SEGMENTS["fc1_bias"]]
    offset += SEGMENTS["fc1_bias"]
    w2 = flat[offset : offset + SEGMENTS["fc2_weights"]]
    offset += SEGMENTS["fc2_weights"]
    b2 = flat[offset : offset + SEGMENTS["fc2_bias"]]

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "weight_fc1_64_16.npy", np.array([_fp_to_float(x) for x in w1], dtype=np.float64).reshape(64, 16))
    np.save(args.out / "bias_fc1_16.npy", np.array([_fp_to_float(x) for x in b1], dtype=np.float64))
    np.save(args.out / "weight_fc2_16_10.npy", np.array([_fp_to_float(x) for x in w2], dtype=np.float64).reshape(16, 10))
    np.save(args.out / "bias_fc2_10.npy", np.array([_fp_to_float(x) for x in b2], dtype=np.float64))

    # registry hint
    reg_path = REPO / "vpin-backend" / "data" / "models" / "registry.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg = {
        "models": [
            {
                "id": "cnn-mnist",
                "name": "CNN (MNIST 预训练)",
                "network": "A",
                "weights_dir": str(args.out),
            }
        ]
    }
    reg_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    print(f"Restored weights to {args.out}")
    print(f"Updated registry {reg_path}")


if __name__ == "__main__":
    main()
