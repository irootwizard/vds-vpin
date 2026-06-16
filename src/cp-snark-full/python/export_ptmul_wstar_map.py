#!/usr/bin/env python3
"""
Map PtMul trajectory index j -> W* index i when trajectory weight equals a W* leaf.

Reads:
  proof_generation/.../rust_files/{network}/pointMult/weight.json
  model_exports/{network}/full_weights.json

Writes:
  model_exports/{network}/j_to_wstar_index.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RUST_FILES = REPO / "src" / "proof_generation" / "vPIN_proof_generation" / "src" / "rust_files"
EXPORTS = Path(__file__).resolve().parents[1] / "model_exports"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A")
    args = p.parse_args()

    weight_path = RUST_FILES / args.network / "pointMult" / "weight.json"
    wstar_path = EXPORTS / args.network / "full_weights.json"
    if not weight_path.is_file():
        raise SystemExit(f"missing {weight_path}")
    if not wstar_path.is_file():
        raise SystemExit(f"missing {wstar_path} — run export_full_weights.py first")

    traj = [int(x) for x in json.loads(weight_path.read_text(encoding="utf-8"))]
    wstar = [int(x) for x in json.loads(wstar_path.read_text(encoding="utf-8"))["w_star_flat"]]

    # value -> first index in W*
    value_to_idx: dict[int, int] = {}
    for i, v in enumerate(wstar):
        if v not in value_to_idx:
            value_to_idx[v] = i

    mapping = []
    for j, w in enumerate(traj):
        idx = value_to_idx.get(w)
        mapping.append(idx if idx is not None else None)

    out = {
        "network_id": args.network,
        "num_ptmul": len(traj),
        "j_to_wstar_index": mapping,
        "direct_hits": sum(1 for m in mapping if m is not None),
    }
    out_path = EXPORTS / args.network / "j_to_wstar_index.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({out['direct_hits']}/{len(traj)} direct W* hits)")


if __name__ == "__main__":
    main()
