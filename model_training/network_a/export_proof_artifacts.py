"""Export Network A proof artifacts from model_training forward (P0).

Produces conv/pool/fc traces aligned with 4×4 sum pool and 32×32 conv grid,
plus full_weights.json (N_W=1219) from checkpoint npy or inline conv + FC.

Default output:
  {run_dir}/proof_artifacts/
Optional mirror:
  src/cp-snark-full/model_exports/A/
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from model_training.network_a.fixed_point import apply_client_action
from model_training.network_a.ec_witness_schedule import (
    EcWitnessMode,
    derive_ec_schedule,
    load_standard_grid_spec,
    write_ec_schedule_bundle,
)
from model_training.network_a.model import CONV_KERNEL, NetworkA, _pool_fixed, _quantize_fc_weight
from model_training.network_a.preprocess import preprocess_batch_uint8
from model_training.network_a.truncation_config import TruncationPlan

CP_SNARK_A = REPO / "src" / "cp-snark-full" / "model_exports" / "A"
STANDARD_RUN = REPO / "model_training" / "outputs" / "20260622_184254"
LEGACY_RUST = (
    REPO
    / "src"
    / "proof_generation"
    / "vPIN_proof_generation"
    / "src"
    / "rust_files"
    / "A"
)
NETWORK_A_W_STAR_LEN = 1219

_VPIN_BACKEND = REPO / "vpin-backend"
if str(_VPIN_BACKEND) not in sys.path:
    sys.path.insert(0, str(_VPIN_BACKEND))


def _int_str(x: int | float) -> str:
    return str(int(x))


def _load_image(mnist_index: int = 0) -> tuple[torch.Tensor, int, int | None]:
    """Official MNIST test sample by index (IDX at model_training/data/mnist/)."""
    _client = REPO / "vpin-client"
    if str(_client) not in sys.path:
        sys.path.insert(0, str(_client))
    from vpin_client.data.preprocess import load_mnist_test

    prep = load_mnist_test(mnist_index)
    images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
    idx = prep.mnist_index if prep.mnist_index is not None else mnist_index
    return images, idx, prep.label


def _conv_windows(
    fixed_input: torch.Tensor, conv_pre_relu: torch.Tensor, *, kernel: int = 3, pad: int = 1
) -> tuple[list[list[str]], list[str], list[str]]:
    """32×32 grid: 3×3 windows aligned with ``F.conv2d(..., padding=pad)`` + pre-ReLU MAC outputs."""
    inp = fixed_input[0, 0].cpu().numpy().astype(np.int64)
    out = conv_pre_relu[0, 0].cpu().numpy().astype(np.int64)
    h, w = inp.shape
    filter_flat = [_int_str(int(v)) for v in CONV_KERNEL[0, 0].flatten().tolist()]
    windows: list[list[str]] = []
    outputs: list[str] = []
    for oy in range(h):
        for ox in range(w):
            win: list[str] = []
            for fi in range(kernel):
                for fj in range(kernel):
                    iy = oy - pad + fi
                    ix = ox - pad + fj
                    if 0 <= iy < h and 0 <= ix < w:
                        win.append(_int_str(int(inp[iy, ix])))
                    else:
                        win.append("0")
            windows.append(win)
            outputs.append(_int_str(int(out[oy, ox])))
    return windows, outputs, filter_flat


def _pool_trace(after_conv_relu: torch.Tensor, plan: TruncationPlan) -> dict[str, Any]:
    """4×4 sum pool → 8×8; matches Network A."""
    x = after_conv_relu[0, 0].cpu().numpy().astype(np.int64)
    k, stride = 4, 4
    oh, ow = x.shape[0] // k, x.shape[1] // k
    windows: list[list[str]] = []
    outputs: list[str] = []
    inv_fp = plan.pool_inv_fp
    for i in range(oh):
        for j in range(ow):
            block = x[i * stride : i * stride + k, j * stride : j * stride + k]
            flat = block.flatten().tolist()
            windows.append([_int_str(v) for v in flat])
            summed = int(block.sum())
            outputs.append(_int_str(summed))
    return {
        "kernel": k,
        "stride": stride,
        "inv_k_squared_fp": _int_str(inv_fp),
        "output_h": oh,
        "output_w": ow,
        "windows": windows,
        "output_flat": outputs,
    }


def _fc_trace(model: NetworkA, after_pool: torch.Tensor) -> dict[str, Any]:
    """FC1 64→16 and FC2 16→10 MAC metadata from one forward."""
    x = after_pool[0].cpu().numpy().astype(np.int64)
    w1 = _quantize_fc_weight(model.fc1.weight.data.cpu().T).numpy().astype(np.int64)
    b1 = _quantize_fc_weight(model.fc1.bias.data.cpu()).numpy().astype(np.int64)
    w2 = _quantize_fc_weight(model.fc2.weight.data.cpu().T).numpy().astype(np.int64)
    b2 = _quantize_fc_weight(model.fc2.bias.data.cpu()).numpy().astype(np.int64)

    h1 = x @ w1 + b1
    h1_relu = np.maximum(h1, 0)
    h2 = h1_relu @ w2 + b2

    def layer_dict(inputs, weights, bias, outputs):
        return {
            "inputs": [_int_str(v) for v in inputs.tolist()],
            "weights_in_out": [[_int_str(weights[i, j]) for j in range(weights.shape[1])] for i in range(weights.shape[0])],
            "bias": [_int_str(v) for v in bias.tolist()],
            "outputs": [_int_str(v) for v in outputs.tolist()],
        }

    return {
        "layers": [
            layer_dict(x, w1, b1, h1),
            layer_dict(h1_relu, w2, b2, h2),
        ],
        "fc1_in": 64,
        "fc1_out": 16,
        "fc2_in": 16,
        "fc2_out": 10,
    }


def _full_weights(model: NetworkA) -> dict[str, Any]:
    conv = CONV_KERNEL[0, 0].flatten().tolist()
    w1 = _quantize_fc_weight(model.fc1.weight.data.cpu().T).flatten().numpy()
    b1 = _quantize_fc_weight(model.fc1.bias.data.cpu()).numpy()
    w2 = _quantize_fc_weight(model.fc2.weight.data.cpu().T).flatten().numpy()
    b2 = _quantize_fc_weight(model.fc2.bias.data.cpu()).numpy()

    def to_u128_list(arr: np.ndarray) -> list[int]:
        out = []
        for x in arr.flatten().tolist():
            v = int(x)
            if v < 0:
                v += 1 << 32
            out.append(v)
        return out

    flat: list[int] = [int(x) for x in conv]
    flat.extend(to_u128_list(w1))
    flat.extend(to_u128_list(b1))
    flat.extend(to_u128_list(w2))
    flat.extend(to_u128_list(b2))
    if len(flat) != NETWORK_A_W_STAR_LEN:
        raise ValueError(f"N_W expected {NETWORK_A_W_STAR_LEN}, got {len(flat)}")
    return {
        "network_id": "A",
        "vpin_version": 1,
        "num_weights": len(flat),
        "w_star_flat": [str(x) for x in flat],
        "meta": {
            "source": "model_training.network_a.export_proof_artifacts",
            "segments": {"conv": 9, "fc1_weights": 1024, "fc1_bias": 16, "fc2_weights": 160, "fc2_bias": 10},
        },
    }


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def export_ec_witness_from_legacy(
    run_dir: Path,
    *,
    legacy_root: Path = LEGACY_RUST,
    apply_rlc: bool = False,
    gamma_mult_hex: str | None = None,
) -> Path:
    """Bootstrap ec_witness/ by copying legacy rust_files (until homomorphic exporter lands)."""
    from vpin_backend.proof.rlc_adapter import apply_gamma_mult_to_fc_weights

    ec_root = run_dir / "proof_artifacts" / "ec_witness"
    ec_root.mkdir(parents=True, exist_ok=True)

    pm_src = legacy_root / "pointMult"
    pa_src = legacy_root / "pointAdd"
    if not pm_src.is_dir():
        raise FileNotFoundError(f"legacy pointMult missing: {pm_src}")

    _copytree(pm_src, ec_root / "pointMult")
    if pa_src.is_dir():
        _copytree(pa_src, ec_root / "pointAdd")

    if apply_rlc:
        if not gamma_mult_hex:
            raise ValueError("apply_rlc requires --gamma-mult hex")
        fw = run_dir / "proof_artifacts" / "full_weights.json"
        if not fw.is_file():
            raise FileNotFoundError(f"need full_weights.json at {fw}")
        w_star = [int(x) for x in json.loads(fw.read_text(encoding="utf-8"))["w_star_flat"]]
        weight_path = ec_root / "pointMult" / "weight.json"
        weights = [int(x) for x in json.loads(weight_path.read_text(encoding="utf-8"))]
        updated = apply_gamma_mult_to_fc_weights(weights, w_star, gamma_mult_hex)
        weight_path.write_text(json.dumps([str(w) for w in updated]), encoding="utf-8")

    return ec_root


def write_ec_witness_manifest(run_dir: Path, model_id: str = "A", mode: str = "paper_proof") -> Path:
    spec = load_standard_grid_spec(run_dir)
    schedule = derive_ec_schedule(spec, EcWitnessMode.PAPER_PROOF)

    manifest = {
        "model_id": model_id,
        "mode": mode,
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
    }
    out = run_dir / "proof_artifacts" / "ec_witness" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def _load_model_weights(run_dir: Path, model: NetworkA, checkpoint: Path | None) -> None:
    ckpt = checkpoint or (run_dir / "checkpoint.pt")
    if ckpt.is_file():
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        model.load_state_dict(payload["state_dict"])
        return
    model.fc1.weight.data = torch.from_numpy(np.load(run_dir / "weight_fc1_64_16.npy"))
    model.fc1.bias.data = torch.from_numpy(np.load(run_dir / "bias_fc1_16.npy"))
    model.fc2.weight.data = torch.from_numpy(np.load(run_dir / "weight_fc2_16_10.npy"))
    model.fc2.bias.data = torch.from_numpy(np.load(run_dir / "bias_fc2_10.npy"))


def export_proof_artifacts(
    run_dir: Path,
    *,
    mirror_cp_snark: bool = False,
    checkpoint: Path | None = None,
    export_rlcr_ec: bool = False,
    mnist_index: int = 0,
    write_ec_schedule: bool = True,
    from_legacy_ec: bool = False,
    apply_rlc: bool = False,
    gamma_mult_hex: str | None = None,
) -> Path:
    run_dir = run_dir.resolve()
    out = run_dir / "proof_artifacts"
    out.mkdir(parents=True, exist_ok=True)

    plan = TruncationPlan()
    if (run_dir / "truncation_config.json").is_file():
        plan = TruncationPlan.load(run_dir / "truncation_config.json")
    model = NetworkA(plan=plan)
    _load_model_weights(run_dir, model, checkpoint)

    images, mnist_idx, label = _load_image(mnist_index)
    _, fixed = preprocess_batch_uint8(images.cpu())
    conv_pre_relu = model._conv_fixed_int(fixed)
    after_conv = apply_client_action(conv_pre_relu, "relu")
    pooled = _pool_fixed(after_conv, plan.pool_inv_fp)
    shifted = apply_client_action(pooled, "shift", shift_bits_val=plan.shift_pool)
    after_pool = shifted.reshape(1, -1)

    windows, conv_out, filter_flat_only = _conv_windows(fixed, conv_pre_relu)
    conv_trace = {
        "filter_flat": filter_flat_only,
        "grid_h": 32,
        "grid_w": 32,
        "num_windows": len(windows),
        "windows": windows,
        "output_flat": conv_out,
    }
    pool_trace = _pool_trace(after_conv, plan)
    fc_trace = _fc_trace(model, after_pool)
    full_weights = _full_weights(model)

    (out / "conv_trace.json").write_text(json.dumps(conv_trace, indent=2), encoding="utf-8")
    (out / "pool_trace.json").write_text(json.dumps(pool_trace, indent=2), encoding="utf-8")
    (out / "fc_trace.json").write_text(json.dumps(fc_trace, indent=2), encoding="utf-8")
    (out / "full_weights.json").write_text(json.dumps(full_weights, indent=2), encoding="utf-8")

    manifest = {
        "network": "A",
        "mnist_index": mnist_idx,
        "label": label,
        "run_dir": str(run_dir),
        "pool_kernel": pool_trace["kernel"],
        "num_conv_windows": len(conv_trace["windows"]),
        "num_pool_windows": len(pool_trace["windows"]),
        "n_w": full_weights["num_weights"],
    }
    (out / "proof_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if mirror_cp_snark:
        CP_SNARK_A.mkdir(parents=True, exist_ok=True)
        for name in ("conv_trace.json", "pool_trace.json", "fc_trace.json", "full_weights.json"):
            shutil.copy2(out / name, CP_SNARK_A / name)

    print(f"Exported proof artifacts -> {out} (conv_windows={manifest['num_conv_windows']}, pool_k={manifest['pool_kernel']})")

    if write_ec_schedule:
        write_ec_schedule_bundle(run_dir, out / "ec_witness_schedule.json")
        print(f"Wrote ec_witness_schedule.json")

    if from_legacy_ec or not (out / "ec_witness" / "pointMult" / "weight.json").is_file():
        export_ec_witness_from_legacy(
            run_dir,
            apply_rlc=apply_rlc,
            gamma_mult_hex=gamma_mult_hex,
        )
        print(f"Exported ec_witness from legacy -> {out / 'ec_witness'}")

    write_ec_witness_manifest(run_dir)
    print("Wrote ec_witness/manifest.json")

    if export_rlcr_ec:
        cp_python = REPO / "src" / "cp-snark-full" / "python"
        if str(cp_python) not in sys.path:
            sys.path.insert(0, str(cp_python))
        from export_rlcr_ec_witness import export_rlcr_ec_witness

        summary = export_rlcr_ec_witness(
            run_dir, network="A", mnist_index=mnist_idx, write_manifest=True
        )
        print(
            f"Exported rLCR EC witness: mnist_index={summary['mnist_index']} "
            f"pt_mul={summary['pt_mul']} (derived={summary['derived_pt_mul']}) "
            f"pt_add={summary['pt_add']} -> {summary['rust_files']}"
        )

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Network A proof artifacts (P0 + EC schedule)")
    parser.add_argument("--run-dir", type=Path, default=STANDARD_RUN)
    parser.add_argument("--mirror-cp-snark", action="store_true")
    parser.add_argument("--export-rlcr-ec", action="store_true", help="Also run headless rLCR EC witness export")
    parser.add_argument("--from-legacy", action="store_true", help="copy rust_files/A into ec_witness/")
    parser.add_argument("--apply-rlc", action="store_true", help="rewrite FC PtMul weights with gamma_mult")
    parser.add_argument("--gamma-mult", dest="gamma_mult", default=None, help="32-byte hex gamma_prime")
    parser.add_argument("--skip-ec-schedule", action="store_true", help="Skip ec_witness_schedule.json bundle")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument(
        "--mnist-index",
        type=int,
        default=0,
        help="Official MNIST test index (IDX); shared by P0 trace and rLCR EC export",
    )
    args = parser.parse_args(argv)
    export_proof_artifacts(
        args.run_dir,
        mirror_cp_snark=args.mirror_cp_snark,
        checkpoint=args.checkpoint,
        export_rlcr_ec=args.export_rlcr_ec,
        mnist_index=args.mnist_index,
        write_ec_schedule=not args.skip_ec_schedule,
        from_legacy_ec=args.from_legacy,
        apply_rlc=args.apply_rlc,
        gamma_mult_hex=args.gamma_mult,
    )

    if args.mirror_cp_snark:
        from vpin_backend.proof.ec_witness_bundle import load_ec_witness_from_run

        bundle = load_ec_witness_from_run(args.run_dir.resolve(), model_id="A")
        print(
            f"Validated bundle: PtMul={bundle.total_pt_mul} PtAdd={bundle.total_pt_add} "
            f"root={bundle.root}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
