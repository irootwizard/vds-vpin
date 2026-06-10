#!/usr/bin/env python3
"""Self-consistent conv_trace.json (Eq.5/9 MAC) for scalar check without live Server."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "model_exports"


def mac_filter_window(flat_f, window):
    return sum(f * w for f, w in zip(flat_f, window))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A")
    args = p.parse_args()

    filter_2d = [[1, 0, 1], [2, 0, 2], [1, 0, 1]]
    flat_f = [x for row in filter_2d for x in row]
    # 6×6 padded grid (stride 1, 3×3 kernel → 4×4 outputs)
    padded = [
        [1, 2, 3, 4, 0, 0],
        [5, 6, 7, 8, 0, 0],
        [9, 10, 11, 12, 0, 0],
        [13, 14, 15, 16, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ]
    stride = 1
    fh, fw = 3, 3
    oh = (len(padded) - fh) // stride + 1
    ow = (len(padded[0]) - fw) // stride + 1
    windows = []
    output_flat = []
    for i in range(oh):
        for j in range(ow):
            win = []
            for ii in range(fh):
                for jj in range(fw):
                    win.append(padded[i * stride + ii][j * stride + jj])
            windows.append([str(x) for x in win])
            output_flat.append(str(mac_filter_window(flat_f, win)))

    payload = {
        "filter_flat": [str(x) for x in flat_f],
        "windows": windows,
        "output_flat": output_flat,
    }
    out = ROOT / args.network / "conv_trace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(output_flat)} cells)")


if __name__ == "__main__":
    main()
