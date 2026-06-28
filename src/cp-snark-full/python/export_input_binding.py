#!/usr/bin/env python3
"""Export fixed-point input scalars for cm_x binding (demo / CI)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "model_exports"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A")
    args = p.parse_args()
    # Toy 28×28 flatten sample (first 16 values non-zero for demo)
    flat = [0] * (28 * 28)
    for i in range(16):
        flat[i] = (i + 1) * 256  # f=16 fixed-point style magnitudes
    payload = {
        "network_id": args.network,
        "input_flat": [str(x) for x in flat],
        "fixed_point_bits": 16,
    }
    out = ROOT / args.network / "input_binding.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(flat)} scalars)")


if __name__ == "__main__":
    main()
