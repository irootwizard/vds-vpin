"""Headless rLCR EC witness export for trained Network A (paper_proof trajectory).

Runs `src/cnn_networks/Server.py` rLCR path in-process with:
  - FC weights/bias from `{run_dir}/*.npy` (trained checkpoint)
  - Same MNIST sample as `export_proof_artifacts` (mnist_index)
  - Client TReLU/shift rounds inlined (no socket)

Writes: `{run_dir}/proof_artifacts/ec_witness/pointMult|pointAdd/*.json`

Spec: docs/cp-snark/Network-A-CP-SNARK-严格算法规范.md §10
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
CNN = REPO / "src" / "cnn_networks"
TABLE_PATH = REPO / "src" / "Pre_computed_table" / "table.pickle"
VERSION = 1  # Network A: 4×4 pool, FC 64→16→10
SHIFT_POOL = 26  # Client.py / paper rLCR path (intrinsic f after pool)
SHIFT_FC1 = 32


def _load_module(name: str, path: Path):
    """Load Server.py / Client.py without requiring socket argv at import."""
    saved = sys.argv[:]
    try:
        if "Server" in path.name:
            sys.argv = ["export_rlcr", str(VERSION), "19999"]
        else:
            sys.argv = ["export_rlcr", "19999"]
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.argv = saved


def _reset_server_globals(srv) -> None:
    srv.points_mult = []
    srv.weights_array = []
    srv.point_one_Add = []
    srv.point_two_Add = []
    srv.conv_trace_windows = []
    srv.conv_trace_output_flat = []
    srv.pool_trace_windows = []
    srv.pool_trace_output_flat = []
    srv.fc_trace_layers = []
    srv.conv_trace_recording = False
    srv.pool_trace_recording = False
    srv.fc_trace_recording = False
    srv.MultiCoreFeature = 0  # deterministic single-core rLCR on Windows


def _load_mnist_fixed(mnist_index: int) -> np.ndarray:
    """(1, 1, 32, 32) int32 fixed-point — same pipeline as export_proof_artifacts."""
    _client = REPO / "vpin-client"
    if str(_client) not in sys.path:
        sys.path.insert(0, str(_client))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from vpin_client.data.preprocess import load_mnist_test

    from model_training.network_a.preprocess import preprocess_batch_uint8

    prep = load_mnist_test(mnist_index)
    images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
    _, fixed = preprocess_batch_uint8(images.cpu())
    return fixed.numpy().astype(np.int32)


def _load_trained_fc(run_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load int32 fixed-point FC weights from compact_weights/ (matches AHE + full_weights.json)."""
    run_dir = run_dir.resolve()
    compact = run_dir / "compact_weights"
    if compact.is_dir():
        return (
            np.load(compact / "weight_fc1_64_16.npy").astype(np.int32),
            np.load(compact / "bias_fc1_16.npy").astype(np.int32),
            np.load(compact / "weight_fc2_16_10.npy").astype(np.int32),
            np.load(compact / "bias_fc2_10.npy").astype(np.int32),
        )
    # Fallback: float npy → int32 fixed (same as model_training quantize)
    scale = 2**16
    return (
        np.trunc(np.load(run_dir / "weight_fc1_64_16.npy") * scale).astype(np.int32),
        np.trunc(np.load(run_dir / "bias_fc1_16.npy") * scale).astype(np.int32),
        np.trunc(np.load(run_dir / "weight_fc2_16_10.npy") * scale).astype(np.int32),
        np.trunc(np.load(run_dir / "bias_fc2_10.npy") * scale).astype(np.int32),
    )


def _patch_fc_for_fixed_weights(srv) -> None:
    """FC layers: weights already int32 fixed — skip realNumbersToFixedPoint double scaling."""

    def FC1(
        weight_fc1,
        bias_fc1,
        curveOrder,
        curveGenerator,
        h,
        encryptedValue_c1,
        encryptedValue_c2,
        identityPoint,
        curveBaseField,
    ):
        print("\n**************************************************")
        print("Server: FC1 started!")
        w_fp = np.asarray(weight_fc1, dtype=np.int32)
        b_fp = np.asarray(bias_fc1, dtype=np.int32)
        outBias_c1, outBias_c2 = srv.encryptBias(b_fp, curveOrder, curveGenerator, h)
        out_c1 = srv.FCLayer(
            encryptedValue_c1, w_fp, outBias_c1, 1, identityPoint, curveBaseField
        )
        out_c2 = srv.FCLayer(
            encryptedValue_c2, w_fp, outBias_c2, 1, identityPoint, curveBaseField
        )
        print("Server: FC1 finished!")
        print("**************************************************")
        return out_c1, out_c2

    def FC2(
        weight_fc2,
        bias_fc2,
        curveOrder,
        curveGenerator,
        h,
        encryptedValue_c1,
        encryptedValue_c2,
        identityPoint,
        curveBaseField,
    ):
        print("\n**************************************************")
        print("Server: FC2 started!")
        w_fp = np.asarray(weight_fc2, dtype=np.int32)
        b_fp = np.asarray(bias_fc2, dtype=np.int32)
        outBias_c1, outBias_c2 = srv.encryptBias(b_fp, curveOrder, curveGenerator, h)
        out_c1 = srv.FCLayer(
            encryptedValue_c1, w_fp, outBias_c1, 1, identityPoint, curveBaseField
        )
        out_c2 = srv.FCLayer(
            encryptedValue_c2, w_fp, outBias_c2, 1, identityPoint, curveBaseField
        )
        print("Server: FC2 finished!")
        print("Server: Number of EC point multiplications:", len(srv.points_mult))
        print("Server: Number of EC point additions:", len(srv.point_one_Add))
        print("**************************************************")
        return out_c1, out_c2

    srv.FC1 = FC1
    srv.FC2 = FC2


def _write_point_mult(ec_root: Path, srv) -> None:
    pm = ec_root / "pointMult"
    pm.mkdir(parents=True, exist_ok=True)
    px = [srv.intToByte(item.x()) for item in srv.points_mult]
    py = [srv.intToByte(item.y()) for item in srv.points_mult]
    weights = [str(x) for x in srv.weights_array]
    (pm / "weight.json").write_text(json.dumps(weights), encoding="utf-8")
    (pm / "point_mult_px_byte.json").write_text(json.dumps(px), encoding="utf-8")
    (pm / "point_mult_py_byte.json").write_text(json.dumps(py), encoding="utf-8")


def _write_point_add(ec_root: Path, srv) -> None:
    pa = ec_root / "pointAdd"
    pa.mkdir(parents=True, exist_ok=True)
    px, py, rx, ry, rz = [], [], [], [], []
    infinity = srv.point_one_Add[0] * 0 if srv.point_one_Add else None
    for item in srv.point_one_Add:
        px.append(srv.intToByte(item.x()))
        py.append(srv.intToByte(item.y()))
    for item in srv.point_two_Add:
        if infinity is not None and item == infinity:
            rz.append(1)
            rx.append(srv.intToByte(0))
            ry.append(srv.intToByte(0))
        else:
            rz.append(0)
            rx.append(srv.intToByte(item.x()))
            ry.append(srv.intToByte(item.y()))
    (pa / "point_add_px_byte.json").write_text(json.dumps(px), encoding="utf-8")
    (pa / "point_add_py_byte.json").write_text(json.dumps(py), encoding="utf-8")
    (pa / "point_add_rx_byte.json").write_text(json.dumps(rx), encoding="utf-8")
    (pa / "point_add_ry_byte.json").write_text(json.dumps(ry), encoding="utf-8")
    (pa / "point_add_rz_byte.json").write_text(json.dumps(rz), encoding="utf-8")


def export_rlcr_ec_witness(
    run_dir: Path,
    *,
    mnist_index: int = 0,
    write_manifest: bool = True,
) -> dict[str, Any]:
    """Run rLCR with trained weights; write ec_witness under run_dir."""
    run_dir = run_dir.resolve()
    ec_root = run_dir / "proof_artifacts" / "ec_witness"

    if not TABLE_PATH.is_file():
        raise FileNotFoundError(f"BSGS table missing: {TABLE_PATH}")

    cal = {}
    trunc = run_dir / "truncation_config.json"
    if trunc.is_file():
        import json as _json

        cal = _json.loads(trunc.read_text(encoding="utf-8")).get("calibration", {})
    fc1_max = float(cal.get("max_after_fc1_pre_relu", 0))
    bsgs_limit = (1 << 30) - 1  # truncation_config.AHE_ABS_SAFE_LIMIT
    if fc1_max > bsgs_limit:
        raise RuntimeError(
            f"trained run FC1 pre-relu max {fc1_max:.0f} exceeds BSGS safe limit {bsgs_limit}; "
            "rLCR EC export (Server.py) cannot decrypt FC1 for this checkpoint. "
            "M1/CPS prove still uses trained full_weights + traces from export_proof_artifacts. "
            "EC px/py requires rLCR+AHE range alignment (future) or extended BSGS table."
        )

    weight_fc1, bias_fc1, weight_fc2, bias_fc2 = _load_trained_fc(run_dir)
    fixed = _load_mnist_fixed(mnist_index)

    cli = _load_module("vpin_client_rlcr", CNN / "Client.py")
    srv = _load_module("vpin_server_rlcr", CNN / "Server.py")
    _reset_server_globals(srv)

    # MAC traces come from export_proof_artifacts (trained fixed-point forward).
    def _conv2_no_mac_trace(enc_c1, enc_c2, identity_point, curve_base):
        print("\n**************************************************")
        print("Server: First conv. layer started!")
        out1 = srv.callConv2_ciphertext(enc_c1, identity_point, curve_base)
        out2 = srv.callConv2_ciphertext(enc_c2, identity_point, curve_base)
        print("Server: First conv. layer finished!")
        print("**************************************************")
        return out1, out2

    def _pool_no_mac_trace(enc_c1, enc_c2, identity_point, kernel_size, stride):
        print("\n**************************************************")
        print("Server: First AvgPooling started!")
        out1 = srv.callAvgPool2d_ciphertext(enc_c1, identity_point, kernel_size, stride)
        out2 = srv.callAvgPool2d_ciphertext(enc_c2, identity_point, kernel_size, stride)
        print("Server: First AvgPooling finished!")
        print("**************************************************")
        return out1, out2

    srv.conv2_ciphertext = _conv2_no_mac_trace
    srv.avgPool_ciphertext = _pool_no_mac_trace
    srv.fc_trace_recording = False
    _patch_fc_for_fixed_weights(srv)

    table = cli.load_table(str(TABLE_PATH))
    curve, curve_base, curve_order, curve_generator, h, random_value_x = cli.keyGen()
    identity_point = curve_generator * 0

    fixed_fp = cli.realNumbersToFixedPointRepresentation(fixed, 1, 16)
    enc_c1, enc_c2 = cli.encryptFixedPointValue(
        fixed_fp, curve, curve_base, curve_order, curve_generator, h, 0
    )

    kernel_size, stride = srv.KERNEL_STRIDE[VERSION]

    # Conv + rLCR
    out_c1, out_c2 = srv.conv2_ciphertext(enc_c1, enc_c2, identity_point, curve_base)
    dec = cli.decrypt_c1_c2(random_value_x, out_c1, out_c2, curve_generator, table, 0)
    relu_out = cli.relu(dec)
    enc_c1, enc_c2 = cli.encryptFixedPointValue(
        relu_out, curve, curve_base, curve_order, curve_generator, h, 0
    )

    # Pool
    pool_c1, pool_c2 = srv.avgPool_ciphertext(enc_c1, enc_c2, identity_point, kernel_size, stride)
    flat_c1, flat_c2 = srv.flattening(pool_c1, pool_c2)
    dec = cli.decrypt_c1_c2(random_value_x, flat_c1, flat_c2, curve_generator, table, 1)
    shifted = cli.shifting(dec, SHIFT_POOL)
    enc_c1, enc_c2 = cli.encryptFixedPointValue(
        shifted, curve, curve_base, curve_order, curve_generator, h, 1
    )

    # FC1
    fc1_c1, fc1_c2 = srv.FC1(
        weight_fc1,
        bias_fc1,
        curve_order,
        curve_generator,
        h,
        enc_c1,
        enc_c2,
        identity_point,
        curve_base,
    )
    dec = cli.decrypt_c1_c2(random_value_x, fc1_c1, fc1_c2, curve_generator, table, 2)
    relu_out = cli.relu(dec)
    shifted = cli.shifting(relu_out, SHIFT_FC1)
    enc_c1, enc_c2 = cli.encryptFixedPointValue(
        shifted, curve, curve_base, curve_order, curve_generator, h, 2
    )

    # FC2 (collects points_mult / point_one_Add)
    srv.FC2(
        weight_fc2,
        bias_fc2,
        curve_order,
        curve_generator,
        h,
        enc_c1,
        enc_c2,
        identity_point,
        curve_base,
    )

    pt_mul = len(srv.points_mult)
    pt_add = len(srv.point_one_Add)

    from model_training.network_a.ec_witness_schedule import (
        EcWitnessMode,
        derive_ec_schedule,
        load_standard_grid_spec,
    )

    schedule = derive_ec_schedule(load_standard_grid_spec(run_dir), EcWitnessMode.PAPER_PROOF)
    if pt_mul != schedule.total_pt_mul:
        raise RuntimeError(
            f"rLCR PtMul {pt_mul} != paper_proof schedule {schedule.total_pt_mul}"
        )
    if pt_add != schedule.total_pt_add:
        raise RuntimeError(
            f"rLCR PtAdd {pt_add} != paper_proof schedule {schedule.total_pt_add}"
        )

    ec_root.mkdir(parents=True, exist_ok=True)
    _write_point_mult(ec_root, srv)
    _write_point_add(ec_root, srv)

    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "mnist_index": mnist_index,
        "pt_mul": pt_mul,
        "pt_add": pt_add,
        "derived_pt_mul": schedule.total_pt_mul,
        "derived_pt_add": schedule.total_pt_add,
        "weight_source": "trained_run_dir_npy",
        "ec_witness": str(ec_root),
    }

    if write_manifest:
        manifest = {
            **summary,
            "mode": "paper_proof",
            "model_id": "A",
            "note": "rLCR from Server.py with trained FC weights",
        }
        (ec_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    from model_training.network_a.ec_witness_schedule import STANDARD_RUN_DIR

    parser = argparse.ArgumentParser(description="Export rLCR EC witness from trained Network A run")
    parser.add_argument("--run-dir", type=Path, default=STANDARD_RUN_DIR)
    parser.add_argument("--mnist-index", type=int, default=0)
    args = parser.parse_args(argv)
    summary = export_rlcr_ec_witness(args.run_dir, mnist_index=args.mnist_index)
    print(
        f"rLCR EC witness: PtMul={summary['pt_mul']} PtAdd={summary['pt_add']} "
        f"-> {summary['ec_witness']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
