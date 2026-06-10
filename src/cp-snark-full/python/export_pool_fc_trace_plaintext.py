#!/usr/bin/env python3
"""Self-consistent pool_trace.json for scalar Eq.7 checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "model_exports"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A")
    args = p.parse_args()

    # 4×4 grid, 2×2 pool stride 2 → 2×2 outputs
    grid = [
        [10, 20, 30, 40],
        [50, 60, 70, 80],
        [90, 100, 110, 120],
        [130, 140, 150, 160],
    ]
    k, s = 2, 2
    inv_fp = 256  # (1/4)*2^10
    windows = []
    output_flat = []
    for i in range(0, len(grid) - k + 1, s):
        for j in range(0, len(grid[0]) - k + 1, s):
            win = []
            ssum = 0
            for ii in range(k):
                for jj in range(k):
                    v = grid[i + ii][j + jj]
                    win.append(str(v))
                    ssum += v
            windows.append(win)
            # Eq.7: homomorphic sum before public × 1/k² (see layer_proof/pool.rs output_sums).
            output_flat.append(str(ssum))

    pool_payload = {
        "kernel": k,
        "stride": s,
        "inv_k_squared_fp": str(inv_fp),
        "windows": windows,
        "output_flat": output_flat,
    }
    fc_payload = {"layers": []}

    base = ROOT / args.network
    base.mkdir(parents=True, exist_ok=True)
    (base / "pool_trace.json").write_text(json.dumps(pool_payload, indent=2), encoding="utf-8")
    (base / "fc_trace.json").write_text(json.dumps(fc_payload, indent=2), encoding="utf-8")
    print(f"Wrote pool_trace.json and fc_trace.json under {base}")


if __name__ == "__main__":
    main()
