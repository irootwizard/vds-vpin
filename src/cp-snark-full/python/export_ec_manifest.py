#!/usr/bin/env python3
"""M4: export EC witness layer manifest for Network A (heuristic layer ranges)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUST_FILES = (
    REPO
    / "proof_generation"
    / "vPIN_proof_generation"
    / "src"
    / "rust_files"
)


def network_a_manifest() -> dict:
    """
    Heuristic layer tags for 178 PtMul (network A).
    Conv dominates early indices; pool/add mixed; FC tail — refine when Server exports labels.
    """
    return {
        "network": "A",
        "num_pt_mul": 178,
        "num_pt_add": 2144,
        "layers": [
            {"kind": "convolution", "index": 0, "pt_mul_start": 0, "pt_mul_end": 16},
            {"kind": "average_pooling", "index": 0, "pt_mul_start": 16, "pt_mul_end": 32},
            {"kind": "fully_connected", "index": 0, "pt_mul_start": 32, "pt_mul_end": 120},
            {"kind": "fully_connected", "index": 1, "pt_mul_start": 120, "pt_mul_end": 178},
        ],
    }


def main() -> None:
    network = sys.argv[1] if len(sys.argv) > 1 else "A"
    if network.upper() != "A":
        print(f"manifest for {network}: only A implemented", file=sys.stderr)
        sys.exit(1)
    out_dir = RUST_FILES / network / "pointMult"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(network_a_manifest(), indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
