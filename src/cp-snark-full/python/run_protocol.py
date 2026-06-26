#!/usr/bin/env python3
"""
CP-SNARK full protocol driver for vPIN.

Phases (paper-aligned):
  1. Setup — E1/E2 curve parameters
  2. Model commitment cm_W — server commits to CNN weights
  3. Input commitment cm_x — client commits to public inputs
  4. Computation — witness from rust_files JSON (point add/mult)
  5. Client random challenge γ
  6. Proof generation — Spartan sub-circuit proofs
  7. Client verification

Does not modify existing src/cnn_networks or vPIN_proof_generation code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CP_SNARK_ROOT = os.path.dirname(SCRIPT_DIR)
RUST_FILES = os.path.normpath(
    os.path.join(
        CP_SNARK_ROOT,
        "..",
        "proof_generation",
        "vPIN_proof_generation",
        "src",
        "rust_files",
    )
)


def curve_e2_info():
    """Same parameters as src/cnn_networks/Client.py::curveE2Info()."""
    return {
        "curveBaseField": 7237005577332262213973186563042994240857116359379907606001950938285454250989,
        "a": 3491403595575449084947959021303599933011749826127899762162894550148391771037,
        "b": 3633908682298454119909199192149978293706667958442512986315258451820769071958,
        "generator_x": 4561981307020378385254256586024830594940985765081274686120783167106442831732,
        "generator_y": 684120277165286233470758410892647831027470652988879249692043589061244861334,
        "curveOrder": 7237005577332262213973186563042994240704759454384003648147593987722918659549,
    }


def load_weights(network: str) -> list[int]:
    path = os.path.join(RUST_FILES, network, "pointMult", "weight.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [int(x) for x in raw]


def run_cargo(subcmd: str, network: str) -> subprocess.CompletedProcess:
    manifest = os.path.join(CP_SNARK_ROOT, "Cargo.toml")
    cmd = ["cargo", "run", "--quiet", "--manifest-path", manifest, "--", subcmd, network]
    return subprocess.run(cmd, cwd=CP_SNARK_ROOT, capture_output=True, text=True)


def main():
    network = sys.argv[1] if len(sys.argv) > 1 else "A"
    print(f"=== CP-SNARK Python driver (network={network}) ===\n")

    e2 = curve_e2_info()
    weights = load_weights(network)
    print(f"[Setup] E2 base field n_2 (curveBaseField) = {e2['curveBaseField']}")
    print(f"[Setup] E2 subgroup order q_2 (curveOrder) = {e2['curveOrder']}")
    print(f"[Setup] Loaded {len(weights)} model weights from witness JSON")

    print("\n[Phase 1-2] Rust setup + commitments...")
    r = run_cargo("setup", network)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

    print("[Phase 3-6] Full protocol (witness + challenge + prove)...")
    r = run_cargo("full", network)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

    print("[Phase 7] Independent client verify pass...")
    r = run_cargo("verify", network)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)

    artifact = os.path.join(CP_SNARK_ROOT, "artifacts", network, "protocol.json")
    with open(artifact, encoding="utf-8") as f:
        data = json.load(f)
    print("\n=== Summary ===")
    print(f"  cm_W digest: {data['model_commitment']['cm_weights']['digest_hex'][:32]}...")
    print(f"  cm_x digest: {data['input_commitment']['cm_public']['digest_hex'][:32]}...")
    print(f"  client γ:    {data['client_challenge']['gamma'][:32]}...")
    print(f"  prove_ms:    {data['prove_time_ms']}")
    print(f"  verify_ms:   {data['verify_time_ms']}")
    print("\nAll CP-SNARK protocol phases completed successfully.")


if __name__ == "__main__":
    main()
