#!/usr/bin/env python3
"""Export ptmul_scalar_sources.json for Network A L1 binding (§11.1)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "model_exports" / "A" / "ptmul_scalar_sources.json"

CONV_KERNEL = 9
FC1_INPUTS = 64
FC1_OUTPUTS = 16
FC2_INPUTS = 16
FC2_OUTPUTS = 10
O_FC1 = 9
O_FC2 = 1049


def j_fc1(beta: int, p: int) -> int:
    return 18 + (beta - 1) * FC1_INPUTS + p


def j_fc2(beta: int, p: int) -> int:
    return 146 + (beta - 1) * FC2_INPUTS + p


def build_sources() -> list[dict]:
    sources: list[dict] = []
    for beta, branch in ((1, "c1"), (2, "c2")):
        for s in range(CONV_KERNEL):
            j = (beta - 1) * CONV_KERNEL + s
            sources.append(
                {
                    "j": j,
                    "kind": "direct_weight",
                    "layer": "conv",
                    "branch": branch,
                    "w_index": s,
                }
            )
    for beta, branch in ((1, "c1"), (2, "c2")):
        for p in range(FC1_INPUTS):
            j = j_fc1(beta, p)
            sources.append(
                {
                    "j": j,
                    "kind": "rlc_weight_column",
                    "layer": "fc1",
                    "branch": branch,
                    "input_index": p,
                    "output_dim": FC1_OUTPUTS,
                    "base_offset": O_FC1,
                    "challenge": "gamma_mult",
                }
            )
    for beta, branch in ((1, "c1"), (2, "c2")):
        for p in range(FC2_INPUTS):
            j = j_fc2(beta, p)
            sources.append(
                {
                    "j": j,
                    "kind": "rlc_weight_column",
                    "layer": "fc2",
                    "branch": branch,
                    "input_index": p,
                    "output_dim": FC2_OUTPUTS,
                    "base_offset": O_FC2,
                    "challenge": "gamma_mult",
                }
            )
    sources.sort(key=lambda x: x["j"])
    return sources


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    payload = {
        "network_id": "A",
        "num_ptmul": 178,
        "spec_doc": "docs/cp-snark/模型参数绑定计算轨迹-数学推导.md §8",
        "sources": build_sources(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({len(payload['sources'])} entries)")


if __name__ == "__main__":
    main()
