#!/usr/bin/env python3
"""
Derive per-layer EC witness counts from the vPIN **paper** (arXiv:2411.07468),
not from Server.py rLCR implementation.

Authoritative spec: docs/cp-snark/论文EC-Witness计数规范-NetworkA.md

Modes:
  - paper_proof: Table I / §V — RLC-compressed CP-SNARK witnesses (178 PtMul @ Network A)
  - ahe_homomorphic: naive homomorphic MAC counts (Eq. 6/7/8), for AHE product path only

Usage:
  python -m model_training.network_a.ec_schedule_cli
  python -m model_training.network_a.ec_schedule_cli --mode paper_proof
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

_VPIN_BACKEND = REPO_ROOT / "vpin-backend"
if str(_VPIN_BACKEND) not in sys.path:
    sys.path.insert(0, str(_VPIN_BACKEND))

from vpin_backend.crypto.ahe.topology import NETWORK_A, NetworkTopology  # noqa: E402

STANDARD_RUN_DIR = REPO_ROOT / "model_training" / "outputs" / "20260622_184254"
PAPER_REF = "Documents/2024-Privacy-Preserving Verifiable Neural Network Inference Service.pdf §IV-B, §V Table I (arXiv:2411.07468v2)"
ELGAMAL_BRANCHES = 2


class EcWitnessMode(str, Enum):
    """Paper proof path vs AHE homomorphic execution path."""

    PAPER_PROOF = "paper_proof"
    AHE_HOMOMORPHIC = "ahe_homomorphic"

    # Deprecated aliases (legacy scripts)
    RLC_COMPRESSED = "paper_proof"
    AHE_NAIVE = "ahe_homomorphic"


@dataclass(frozen=True)
class NetworkAGridSpec:
    """Spatial grid for one inference (model_training standard: 32x32 padded MNIST)."""

    input_n: int = 32
    topology: NetworkTopology = field(default_factory=lambda: NETWORK_A)
    elgamal_branches: int = ELGAMAL_BRANCHES

    @property
    def conv(self):
        return self.topology.conv

    @property
    def pool(self):
        return self.topology.pools[0]

    @property
    def conv_out_side(self) -> int:
        """n' with explicit padding (topology.conv.padding)."""
        c = self.conv
        return (self.input_n + 2 * c.padding - c.kernel_h) // c.stride + 1

    @property
    def conv_num_windows(self) -> int:
        side = self.conv_out_side
        return side * side

    @property
    def pool_out_side(self) -> int:
        p = self.pool
        side = self.conv_out_side
        return (side - p.kernel_h) // p.stride + 1

    @property
    def pool_num_cells(self) -> int:
        s = self.pool_out_side
        return s * s

    @property
    def pool_flat_dim(self) -> int:
        return self.pool_num_cells * self.conv.in_channels


@dataclass
class LayerEcCounts:
    layer_id: str
    kind: str
    pt_mul: int = 0
    pt_add: int = 0
    pt_mul_start: int = 0
    pt_mul_end: int = 0
    pt_add_start: int = 0
    pt_add_end: int = 0
    paper_formula: str = ""
    notes: str = ""


@dataclass
class NetworkAEcSchedule:
    network_id: str
    topology_id: str
    mode: EcWitnessMode
    paper_ref: str
    grid: dict[str, int]
    elgamal_branches: int
    layers: list[LayerEcCounts]
    total_pt_mul: int
    total_pt_add: int
    derivation: str
    cross_check: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value if isinstance(self.mode, EcWitnessMode) else str(self.mode)
        return d


def load_standard_grid_spec(
    run_dir: Path | None = None,
    *,
    input_n: int | None = None,
) -> NetworkAGridSpec:
    run_dir = run_dir or STANDARD_RUN_DIR
    n = 32
    conv_trace = run_dir / "proof_artifacts" / "conv_trace.json"
    if conv_trace.is_file():
        data = json.loads(conv_trace.read_text(encoding="utf-8"))
        gh = int(data.get("grid_h", n))
        gw = int(data.get("grid_w", n))
        if gh != gw:
            raise ValueError(f"non-square grid {gh}x{gw}")
        n = gh
    if input_n is not None:
        n = input_n

    spec = NetworkAGridSpec(input_n=n)
    manifest = run_dir / "proof_artifacts" / "proof_manifest.json"
    if manifest.is_file():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        expected = m.get("num_conv_windows")
        if expected is not None and int(expected) != spec.conv_num_windows:
            raise ValueError(
                f"manifest num_conv_windows={expected} != derived {spec.conv_num_windows}"
            )
    return spec


def _assign_ranges(layers: list[LayerEcCounts]) -> None:
    mul_off = add_off = 0
    for layer in layers:
        layer.pt_mul_start = mul_off
        mul_off += layer.pt_mul
        layer.pt_mul_end = mul_off
        layer.pt_add_start = add_off
        add_off += layer.pt_add
        layer.pt_add_end = add_off


def derive_paper_proof_layers(spec: NetworkAGridSpec) -> list[LayerEcCounts]:
    """
    vPIN paper Table I / §V (RLC-compressed proof witnesses).

    Conv:  B * k^2 PtMul,  B * (k^2 - 1) PtAdd
    Pool:  0 PtMul,         B * (k_hat^2 - 1) * N_pool PtAdd
    FC:    B * g PtMul,     B * ((g - 1) + h) PtAdd  per layer
    """
    B = spec.elgamal_branches
    k = spec.conv.kernel_h
    k2 = k * k
    k_hat = spec.pool.kernel_h
    n_pool = spec.pool_num_cells

    layers: list[LayerEcCounts] = [
        LayerEcCounts(
            layer_id="conv",
            kind="convolution",
            pt_mul=B * k2,
            pt_add=B * (k2 - 1),
            paper_formula="Table I Conv: O(k^2) PtMul, O(k^2) PtAdd after Eq.(9)",
            notes=f"B={B}, k={k}; independent of {spec.conv_num_windows} windows",
        ),
        LayerEcCounts(
            layer_id="pool",
            kind="average_pooling",
            pt_mul=0,
            pt_add=B * (k_hat * k_hat - 1) * n_pool,
            paper_formula="Table I Avg Pool: 0 PtMul; (k^2-1)*N_pool PtAdd for Eq.(7) sum",
            notes=f"B={B}, pool_cells={n_pool}, k_hat={k_hat}",
        ),
    ]

    for idx, fc in enumerate(spec.topology.fcs, start=1):
        g, h = fc.in_features, fc.out_features
        layers.append(
            LayerEcCounts(
                layer_id=f"fc{idx}",
                kind="fully_connected",
                pt_mul=B * g,
                pt_add=B * ((g - 1) + h),
                paper_formula="Table I FC: O(g) PtMul, O(g+h) PtAdd after Eq.(10)",
                notes=f"B={B}, g={g}, h={h}",
            )
        )
    return layers


def derive_ahe_homomorphic_layers(spec: NetworkAGridSpec) -> list[LayerEcCounts]:
    """Naive homomorphic MAC (Eq. 6/7/8) — not the paper proof witness count."""
    B = spec.elgamal_branches
    k2 = spec.conv.kernel_h * spec.conv.kernel_w
    windows = spec.conv_num_windows
    k_hat2 = spec.pool.kernel_h * spec.pool.kernel_w
    n_pool = spec.pool_num_cells

    layers: list[LayerEcCounts] = [
        LayerEcCounts(
            layer_id="conv",
            kind="convolution",
            pt_mul=B * windows * k2,
            pt_add=B * windows * (k2 - 1),
            paper_formula="Eq.(6) per-cell MAC (not proof-compressed)",
            notes=f"{windows} windows x k^2 x B={B}",
        ),
        LayerEcCounts(
            layer_id="pool",
            kind="average_pooling",
            pt_mul=B * n_pool,
            pt_add=B * (k_hat2 - 1) * n_pool,
            paper_formula="Eq.(7) sum + public scale (scale -> PtMul in AHE path)",
            notes=f"{n_pool} cells; scale 1/k_hat^2 counted as PtMul",
        ),
    ]

    for idx, fc in enumerate(spec.topology.fcs, start=1):
        g, h = fc.in_features, fc.out_features
        mac_mul = g * h
        mac_add = g * h  # MAC adds + bias add per output (homomorphic_network_a style)
        layers.append(
            LayerEcCounts(
                layer_id=f"fc{idx}",
                kind="fully_connected",
                pt_mul=B * mac_mul,
                pt_add=B * mac_add,
                paper_formula="Eq.(8) full MAC (not Eq.(10) compressed)",
                notes=f"g={g}, h={h}, B={B}",
            )
        )
    return layers


def derive_ec_schedule(
    spec: NetworkAGridSpec | None = None,
    mode: EcWitnessMode = EcWitnessMode.PAPER_PROOF,
    *,
    run_dir: Path | None = None,
) -> NetworkAEcSchedule:
    spec = spec or load_standard_grid_spec(run_dir)

    if mode in (EcWitnessMode.PAPER_PROOF, EcWitnessMode.RLC_COMPRESSED):
        mode = EcWitnessMode.PAPER_PROOF
        layers = derive_paper_proof_layers(spec)
        derivation = "vPIN paper Table I / §V (Eq. 9/7/10 RLC-compressed proof)"
    else:
        mode = EcWitnessMode.AHE_HOMOMORPHIC
        layers = derive_ahe_homomorphic_layers(spec)
        derivation = "AHE naive homomorphic MAC (Eq. 6/7/8); not paper proof count"

    _assign_ranges(layers)
    total_mul = sum(l.pt_mul for l in layers)
    total_add = sum(l.pt_add for l in layers)

    cross_check: dict[str, Any] = {
        "legacy_rust_files_anchor": {"pt_mul": 178, "pt_add": 2144},
        "paper_proof_matches_legacy_ptmul": (
            mode == EcWitnessMode.PAPER_PROOF and total_mul == 178
        ),
        "paper_proof_matches_legacy_ptadd": (
            mode == EcWitnessMode.PAPER_PROOF and total_add == 2144
        ),
        "ahe_conv_pool_ptmul": None,
    }
    if mode == EcWitnessMode.AHE_HOMOMORPHIC:
        cross_check["ahe_conv_pool_ptmul"] = layers[0].pt_mul + layers[1].pt_mul

    return NetworkAEcSchedule(
        network_id=spec.topology.network_id,
        topology_id="cnn_mnist_v1",
        mode=mode,
        paper_ref=PAPER_REF,
        grid={
            "input_n": spec.input_n,
            "conv_out_side": spec.conv_out_side,
            "conv_num_windows": spec.conv_num_windows,
            "pool_out_side": spec.pool_out_side,
            "pool_num_cells": spec.pool_num_cells,
            "pool_flat_dim": spec.pool_flat_dim,
        },
        elgamal_branches=spec.elgamal_branches,
        layers=layers,
        total_pt_mul=total_mul,
        total_pt_add=total_add,
        derivation=derivation,
        cross_check=cross_check,
    )


def write_ec_schedule_json(schedule: NetworkAEcSchedule, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(schedule.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def derive_paper_proof_schedule(
    spec: NetworkAGridSpec | None = None,
    *,
    run_dir: Path | None = None,
) -> NetworkAEcSchedule:
    """Alias for vpin_backend.inference.ec_schedule fallback derive."""
    return derive_ec_schedule(spec, EcWitnessMode.PAPER_PROOF, run_dir=run_dir)


def write_ec_schedule_bundle(run_dir: Path, out_path: Path) -> None:
    """Write paper_proof + ahe_homomorphic schedules (multi-mode JSON bundle)."""
    spec = load_standard_grid_spec(run_dir)
    bundle: dict[str, Any] = {
        "run_dir": str(run_dir.resolve()),
        "schedules": {},
    }
    for mode in (EcWitnessMode.PAPER_PROOF, EcWitnessMode.AHE_HOMOMORPHIC):
        sched = derive_ec_schedule(spec, mode)
        bundle["schedules"][mode.value] = sched.to_dict()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_schedule(schedule: NetworkAEcSchedule) -> None:
    g = schedule.grid
    print(f"Network {schedule.network_id} | mode={schedule.mode.value}")
    print(f"Paper: {schedule.paper_ref}")
    print(
        f"Grid n={g['input_n']} -> conv {g['conv_out_side']}x{g['conv_out_side']} "
        f"({g['conv_num_windows']} win) -> pool {g['pool_out_side']}x{g['pool_out_side']} "
        f"({g['pool_num_cells']} cells, flat {g['pool_flat_dim']})"
    )
    print(f"ElGamal branches B={schedule.elgamal_branches}")
    print()
    hdr = f"{'layer':<6} {'kind':<18} {'PtMul':>8} {'PtAdd':>8}  mul_range    paper_formula"
    print(hdr)
    print("-" * len(hdr))
    for layer in schedule.layers:
        formula = (layer.paper_formula or "")[:36]
        print(
            f"{layer.layer_id:<6} {layer.kind:<18} {layer.pt_mul:>8} {layer.pt_add:>8}  "
            f"[{layer.pt_mul_start},{layer.pt_mul_end})  {formula}"
        )
    print("-" * len(hdr))
    print(f"{'TOTAL':<6} {'':<18} {schedule.total_pt_mul:>8} {schedule.total_pt_add:>8}")
    cc = schedule.cross_check
    if schedule.mode == EcWitnessMode.PAPER_PROOF:
        print(
            f"\nLegacy rust_files anchor: PtMul=178 match={cc['paper_proof_matches_legacy_ptmul']}, "
            f"PtAdd=2144 match={cc['paper_proof_matches_legacy_ptadd']}"
        )
    else:
        print(f"\nAHE conv+pool PtMul={cc.get('ahe_conv_pool_ptmul')}")
    print(f"Derivation: {schedule.derivation}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive Network A EC witness schedule from vPIN paper formulas"
    )
    parser.add_argument("--run-dir", type=Path, default=STANDARD_RUN_DIR)
    parser.add_argument(
        "--mode",
        choices=["paper_proof", "ahe_homomorphic", "both"],
        default="both",
    )
    parser.add_argument("--input-n", type=int, default=None, help="override input side length")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    spec = load_standard_grid_spec(args.run_dir, input_n=args.input_n)
    modes = (
        [EcWitnessMode.PAPER_PROOF, EcWitnessMode.AHE_HOMOMORPHIC]
        if args.mode == "both"
        else [EcWitnessMode(args.mode)]
    )

    bundle: dict[str, Any] = {
        "run_dir": str(args.run_dir.resolve()),
        "paper_ref": PAPER_REF,
        "spec_doc": "docs/cp-snark/论文EC-Witness计数规范-NetworkA.md",
        "grid": {
            "input_n": spec.input_n,
            "conv_out_side": spec.conv_out_side,
            "conv_num_windows": spec.conv_num_windows,
            "pool_num_cells": spec.pool_num_cells,
        },
        "schedules": {},
    }

    for mode in modes:
        schedule = derive_ec_schedule(spec, mode)
        _print_schedule(schedule)
        print()
        bundle["schedules"][mode.value] = schedule.to_dict()

    out = args.out or (args.run_dir / "proof_artifacts" / "ec_witness_schedule.json")
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0
