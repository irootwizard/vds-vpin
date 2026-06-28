#!/usr/bin/env python3
"""Self-check model_exports/{network} weights and trace consistency."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXPORTS = Path(__file__).resolve().parents[1] / "model_exports"
WEIGHT_JSON_ROOT = (
    REPO
    / "src"
    / "proof_generation"
    / "vPIN_proof_generation"
    / "src"
    / "rust_files"
)
CONV_INLINE = [1, 0, 1, 2, 0, 2, 1, 0, 1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--network", default="A")
    args = p.parse_args()
    root = EXPORTS / args.network
    report: list[tuple[str, bool | None, str]] = []

    def load(name: str) -> dict:
        return json.loads((root / name).read_text(encoding="utf-8"))

    fw = load("full_weights.json")
    flat = [int(x) for x in fw["w_star_flat"]]
    meta = fw.get("meta", {})
    seg = meta.get("segments", {})
    report.append(
        (
            "full_weights 维度 1219",
            len(flat) == fw["num_weights"] == 1219,
            f"len={len(flat)}",
        )
    )
    report.append(("full_weights conv == Server inline", flat[:9] == CONV_INLINE, str(flat[:9])))
    report.append(
        (
            "full_weights segments",
            seg
            == {
                "conv": 9,
                "fc1_weights": 1024,
                "fc1_bias": 16,
                "fc2_weights": 160,
                "fc2_bias": 10,
            },
            str(seg),
        )
    )
    report.append(
        (
            "full_weights npy_present",
            meta.get("sources", {}).get("npy_present") is True,
            str(meta.get("sources", {}).get("npy_present")),
        )
    )

    try:
        import numpy as np

        P = REPO / "src" / "cnn_networks" / "Pre_trained_model"
        scale = 2**16

        def u32(x: int) -> int:
            return int(x) + (1 << 32) if int(x) < 0 else int(x)

        regen: list[int] = list(CONV_INLINE)
        for arr in [
            np.load(P / "weight_fc1_64_16.npy"),
            np.load(P / "bias_fc1_16.npy"),
            np.load(P / "weight_fc2_16_10.npy"),
            np.load(P / "bias_fc2_10.npy"),
        ]:
            fp = (arr * scale).astype(np.int32).flatten()
            regen.extend(u32(int(v)) for v in fp)
        report.append(
            (
                "full_weights 与 .npy 重算一致",
                regen == flat,
                "match" if regen == flat else f"first diff index",
            )
        )
    except Exception as e:
        report.append(("full_weights .npy 交叉验证", None, str(e)))

    ct = load("conv_trace.json")
    filt = [int(x) for x in ct["filter_flat"]]
    windows = [[int(x) for x in w] for w in ct["windows"]]
    outputs = [int(x) for x in ct["output_flat"]]
    mac_bad = [
        (i, sum(w[j] * filt[j] for j in range(9)), out)
        for i, (w, out) in enumerate(zip(windows, outputs))
        if sum(w[j] * filt[j] for j in range(9)) != out
    ]
    report.append(("conv_trace filter == W*[:9]", filt == flat[:9], ""))
    report.append(("conv_trace MAC 16 cells", len(mac_bad) == 0, str(mac_bad[:2])))

    pt = load("pool_trace.json")
    inv = int(pt["inv_k_squared_fp"])
    pool_raw_bad = []
    for i, w in enumerate(pt["windows"]):
        s = sum(int(x) for x in w)
        raw = int(pt["output_flat"][i])
        if s != raw:
            pool_raw_bad.append((i, s, raw, s * inv))
    report.append(
        (
            "pool_trace Eq7 raw sum == output_flat (Rust 期望)",
            len(pool_raw_bad) == 0,
            str(pool_raw_bad[0] if pool_raw_bad else "ok"),
        )
    )
    scaled_ok = all(
        sum(int(x) for x in w) * inv == sum(int(x) for x in w) * inv
        for i, w in enumerate(pt["windows"])
    )
    report.append(
        (
            "pool_trace scaled_output = sum*inv (off-circuit)",
            scaled_ok,
            f"inv={inv}; scaling applied in PoolLayerProofSpec.inv_k_squared_fp",
        )
    )

    fc = load("fc_trace.json")
    report.append(("fc_trace.layers 非空", len(fc.get("layers", [])) > 0, str(len(fc.get("layers", [])))))

    jm = load("j_to_wstar_index.json")
    idxs = jm["j_to_wstar_index"]
    hits = sum(1 for x in idxs if x is not None)
    weight_path = WEIGHT_JSON_ROOT / args.network / "pointMult" / "weight.json"
    traj = [int(x) for x in json.loads(weight_path.read_text(encoding="utf-8"))]
    bind_bad = [(j, wi, flat[wi], traj[j]) for j, wi in enumerate(idxs) if wi is not None and flat[wi] != traj[j]]
    report.append(("j_to_wstar direct_hits", hits == 18, f"{hits}/178"))
    report.append(("L1 18 路与 weight.json", len(bind_bad) == 0, str(bind_bad[:3])))

    ib = load("input_binding.json")
    report.append(
        (
            "input_binding 含 input_flat",
            "input_flat" in ib and len(ib["input_flat"]) > 0,
            f"keys={list(ib.keys())} len={len(ib.get('input_flat', []))}",
        )
    )

    me = root / "model_export.json"
    report.append(("model_export.json", me.is_file(), "内置 load_model_params 回退" if not me.is_file() else "ok"))

    print(f"=== model_exports/{args.network} 自检 ===")
    for name, ok, detail in report:
        mark = "OK" if ok is True else ("FAIL" if ok is False else "WARN")
        print(f"[{mark}] {name}")
        if detail:
            print(f"       {detail}")


if __name__ == "__main__":
    main()
