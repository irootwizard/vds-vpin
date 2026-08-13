"""Paper-proof EC witness: PtMul weight.json from W* + schedule (no legacy copy).

Spec: docs/cp-snark/Network-A-CP-SNARK-严格算法规范.md §6, §10

Conv slots j in [0,18): a_j = W*[j mod 9] (ElGamal B=2 branches).
FC slots: placeholders (0); prove-time sync_ptmul_weights_for_challenge writes gamma' RLC columns.

EC coordinates (px/py, pointAdd) must already exist — rLCR-aligned homomorphic trajectory.
Use --bootstrap-ec-coordinates once to copy regression anchor from rust_files/A (explicit opt-in).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.network_a.ec_witness_schedule import (
    EcWitnessMode,
    derive_ec_schedule,
    load_standard_grid_spec,
)

LEGACY_RUST = (
    REPO
    / "src"
    / "proof_generation"
    / "vPIN_proof_generation"
    / "src"
    / "rust_files"
    / "A"
)

CONV_KERNEL_LEN = 9
ELGAMAL_BRANCHES = 2
FC1_PT_MUL = 128  # 64 inputs × 2 branches
FC2_PT_MUL = 32  # 16 inputs × 2 branches


def _load_w_star(run_dir: Path) -> list[int]:
    fw = run_dir / "proof_artifacts" / "full_weights.json"
    if not fw.is_file():
        raise FileNotFoundError(f"full_weights.json missing: {fw}")
    data = json.loads(fw.read_text(encoding="utf-8"))
    return [int(x) for x in data["w_star_flat"]]


def build_ptmul_weight_skeleton(w_star: list[int], total_pt_mul: int) -> list[int]:
    """Build weight.json from W* conv leaves; FC slots zero until prove sync."""
    if len(w_star) < 9:
        raise ValueError(f"W* too short for conv: {len(w_star)}")
    conv = w_star[:CONV_KERNEL_LEN]
    weights: list[int] = []
    for _branch in range(ELGAMAL_BRANCHES):
        weights.extend(conv)
    fc_len = total_pt_mul - len(weights)
    if fc_len != FC1_PT_MUL + FC2_PT_MUL:
        raise ValueError(
            f"unexpected FC PtMul count {fc_len}; expected {FC1_PT_MUL + FC2_PT_MUL}"
        )
    weights.extend([0] * fc_len)
    if len(weights) != total_pt_mul:
        raise ValueError(f"weight skeleton len {len(weights)} != schedule {total_pt_mul}")
    return weights


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def bootstrap_ec_coordinates_from_legacy(ec_root: Path, *, legacy_root: Path = LEGACY_RUST) -> None:
    """One-time copy of rLCR regression EC coordinates (px/py, pointAdd). Explicit opt-in only."""
    pm_src = legacy_root / "pointMult"
    pa_src = legacy_root / "pointAdd"
    if not pm_src.is_dir():
        raise FileNotFoundError(f"legacy pointMult missing: {pm_src}")
    ec_root.mkdir(parents=True, exist_ok=True)
    _copytree(pm_src, ec_root / "pointMult")
    if pa_src.is_dir():
        _copytree(pa_src, ec_root / "pointAdd")


def _require_ec_coordinates(ec_root: Path) -> None:
    pm = ec_root / "pointMult"
    for name in ("point_mult_px_byte.json", "point_mult_py_byte.json", "weight.json"):
        if not (pm / name).is_file():
            raise FileNotFoundError(
                f"EC coordinate file missing: {pm / name}. "
                "Run with --bootstrap-ec-coordinates (once) or homomorphic exporter."
            )


def export_paper_proof_ec_witness(
    run_dir: Path,
    *,
    model_id: str = "A",
    bootstrap_ec_coordinates: bool = False,
    legacy_root: Path = LEGACY_RUST,
) -> Path:
    """Write ec_witness/ weight.json from W*; validate or bootstrap px/py."""
    run_dir = run_dir.resolve()
    ec_root = run_dir / "proof_artifacts" / "ec_witness"

    if bootstrap_ec_coordinates:
        bootstrap_ec_coordinates_from_legacy(ec_root, legacy_root=legacy_root)

    spec = load_standard_grid_spec(run_dir)
    schedule = derive_ec_schedule(spec, EcWitnessMode.PAPER_PROOF)
    w_star = _load_w_star(run_dir)

    if not (ec_root / "pointMult").is_dir():
        raise FileNotFoundError(
            f"ec_witness/pointMult missing at {ec_root}. "
            "Use --bootstrap-ec-coordinates for regression anchor."
        )
    _require_ec_coordinates(ec_root)

    weights = build_ptmul_weight_skeleton(w_star, schedule.total_pt_mul)
    weight_path = ec_root / "pointMult" / "weight.json"
    weight_path.write_text(json.dumps([str(w) for w in weights]), encoding="utf-8")

    manifest = {
        "model_id": model_id,
        "mode": "paper_proof",
        "total_pt_mul": schedule.total_pt_mul,
        "total_pt_add": schedule.total_pt_add,
        "layers": [
            {
                "layer_id": layer.layer_id,
                "kind": layer.kind,
                "pt_mul_start": layer.pt_mul_start,
                "pt_mul_end": layer.pt_mul_end,
                "pt_add_start": layer.pt_add_start,
                "pt_add_end": layer.pt_add_end,
            }
            for layer in schedule.layers
        ],
        "weight_source": "paper_proof_witness_exporter.W_star_conv",
        "note": "FC PtMul slots filled at prove via sync_ptmul_weights_for_challenge(gamma_prime)",
    }
    (ec_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return ec_root


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Paper-proof EC witness exporter (W* → weight.json)")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--bootstrap-ec-coordinates",
        action="store_true",
        help="explicit one-time copy of rLCR px/py from rust_files/A",
    )
    args = parser.parse_args(argv)
    out = export_paper_proof_ec_witness(
        args.run_dir,
        bootstrap_ec_coordinates=args.bootstrap_ec_coordinates,
    )
    print(f"paper_proof ec_witness -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
