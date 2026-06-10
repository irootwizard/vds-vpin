#!/usr/bin/env python3
"""
Flatten full static model W* for vPIN networks (conv + FC weights + biases).

Order (manifest-fixed, network A):
  conv_filter_flat (9)
  + fc1_weights row-major C-order (64×16 = 1024)
  + fc1_bias (16)
  + fc2_weights (16×10 = 160)
  + fc2_bias (10)
  => 1219 scalars for network A (version 1).

Reads .npy from cnn_networks/Pre_trained_model when present; otherwise writes
deterministic placeholder FC tensors (same shapes) for CI without artifact files.

Usage (repo root):
  python src/cp-snark-full/python/export_full_weights.py --network A
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
CNN_DIR = REPO_ROOT / "src" / "cnn_networks"
PRETRAINED = CNN_DIR / "Pre_trained_model"

NETWORK_VERSION = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}

MODEL_PATHS = {
    1: {
        "weight_fc1": PRETRAINED / "weight_fc1_64_16.npy",
        "bias_fc1": PRETRAINED / "bias_fc1_16.npy",
        "weight_fc2": PRETRAINED / "weight_fc2_16_10.npy",
        "bias_fc2": PRETRAINED / "bias_fc2_10.npy",
        "conv": np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64),
    },
    2: {
        "weight_fc1": PRETRAINED / "weight_fc1_64_32.npy",
        "bias_fc1": PRETRAINED / "bias_fc1_32.npy",
        "weight_fc2": PRETRAINED / "weight_fc2_32_10.npy",
        "bias_fc2": PRETRAINED / "bias_fc2_10.npy",
        "conv": np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64),
    },
    3: {
        "weight_fc1": PRETRAINED / "weight_fc1_256_16.npy",
        "bias_fc1": PRETRAINED / "bias_fc1_16.npy",
        "weight_fc2": PRETRAINED / "weight_fc2_16_10.npy",
        "bias_fc2": PRETRAINED / "bias_fc2_10.npy",
        "conv": np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64),
    },
    4: {
        "weight_fc1": PRETRAINED / "weight_fc1_256_32.npy",
        "bias_fc1": PRETRAINED / "bias_fc1_32.npy",
        "weight_fc2": PRETRAINED / "weight_fc2_32_10.npy",
        "bias_fc2": PRETRAINED / "bias_fc2_10.npy",
        "conv": np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64),
    },
    5: {
        "weight_fc1": PRETRAINED / "weight_fc1_256_64.npy",
        "bias_fc1": PRETRAINED / "bias_fc1_64.npy",
        "weight_fc2": PRETRAINED / "weight_fc2_64_10.npy",
        "bias_fc2": PRETRAINED / "bias_fc2_10.npy",
        "conv": np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64),
    },
}

EXPECTED_NW = {1: 1219, 2: None, 3: None, 4: None, 5: None}  # only A validated in docs


def real_numbers_to_fixed_point(input_arr: np.ndarray, bits: int = 16) -> np.ndarray:
    """Match Server.py realNumbersToFixedPointRepresentation(..., type=1, bits=16)."""
    scale = 2**bits
    return (input_arr * scale).astype(np.int32)


def _load_or_placeholder(path: Path, shape: tuple[int, ...], seed: int) -> np.ndarray:
    if path.is_file():
        return np.load(path)
    rng = np.random.default_rng(seed)
    # Small floats → fixed-point ints after scaling (deterministic per network)
    return rng.uniform(-0.5, 0.5, size=shape).astype(np.float64)


def flatten_w_star(version: int) -> tuple[list[int], dict]:
    spec = MODEL_PATHS[version]
    conv = spec["conv"].flatten().tolist()

    w1 = _load_or_placeholder(spec["weight_fc1"], _shape_from_name(spec["weight_fc1"]), version * 1000 + 1)
    b1 = _load_or_placeholder(spec["bias_fc1"], (_shape_from_name(spec["bias_fc1"])[0],), version * 1000 + 2)
    w2 = _load_or_placeholder(spec["weight_fc2"], _shape_from_name(spec["weight_fc2"]), version * 1000 + 3)
    b2 = _load_or_placeholder(spec["bias_fc2"], (_shape_from_name(spec["bias_fc2"])[0],), version * 1000 + 4)

    w1_fp = real_numbers_to_fixed_point(w1)
    b1_fp = real_numbers_to_fixed_point(b1)
    w2_fp = real_numbers_to_fixed_point(w2)
    b2_fp = real_numbers_to_fixed_point(b2)

    def to_u128_list(arr: np.ndarray) -> list[int]:
        out = []
        for x in arr.flatten().tolist():
            v = int(x)
            if v < 0:
                # int32 two's complement → unsigned u128 for Rust embed
                v = v + (1 << 32)
            out.append(v)
        return out

    flat: list[int] = []
    flat.extend(int(x) for x in conv)
    flat.extend(to_u128_list(w1_fp))
    flat.extend(to_u128_list(b1_fp))
    flat.extend(to_u128_list(w2_fp))
    flat.extend(to_u128_list(b2_fp))

    meta = {
        "version": version,
        "num_weights": len(flat),
        "segments": {
            "conv": len(conv),
            "fc1_weights": w1_fp.size,
            "fc1_bias": b1_fp.size,
            "fc2_weights": w2_fp.size,
            "fc2_bias": b2_fp.size,
        },
        "sources": {
            "weight_fc1": str(spec["weight_fc1"]),
            "bias_fc1": str(spec["bias_fc1"]),
            "weight_fc2": str(spec["weight_fc2"]),
            "bias_fc2": str(spec["bias_fc2"]),
            "npy_present": all(p.is_file() for p in [
                spec["weight_fc1"], spec["bias_fc1"], spec["weight_fc2"], spec["bias_fc2"]
            ]),
        },
    }
    return flat, meta


def _shape_from_name(path: Path) -> tuple[int, ...]:
    name = path.stem
    # e.g. weight_fc1_64_16 → (64, 16)
    parts = name.split("_")
    if len(parts) >= 2 and parts[-2].isdigit() and parts[-1].isdigit():
        return (int(parts[-2]), int(parts[-1]))
    if parts[-1].isdigit():
        return (int(parts[-1]),)
    raise ValueError(f"cannot infer shape from {path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A", choices=list(NETWORK_VERSION))
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: model_exports/{net}/full_weights.json)",
    )
    args = p.parse_args()
    version = NETWORK_VERSION[args.network]
    flat, meta = flatten_w_star(version)

    if EXPECTED_NW.get(version) is not None and len(flat) != EXPECTED_NW[version]:
        raise SystemExit(
            f"network {args.network}: expected N_W={EXPECTED_NW[version]}, got {len(flat)}"
        )

    out = args.out or (
        Path(__file__).resolve().parents[1] / "model_exports" / args.network / "full_weights.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "network_id": args.network,
        "vpin_version": version,
        "num_weights": len(flat),
        "w_star_flat": [str(x) for x in flat],
        "meta": meta,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(flat)} weights to {out}")
    if not meta["sources"]["npy_present"]:
        print("NOTE: .npy files missing — used deterministic placeholder FC weights.")


if __name__ == "__main__":
    main()
