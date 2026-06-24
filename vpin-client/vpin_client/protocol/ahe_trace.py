"""Structured trace helpers for AHE WebSocket sessions (UI / debug)."""

from __future__ import annotations

from typing import Any

import numpy as np

# Network A phase → layer semantics (aligned with topology.py)
PHASE_META: dict[str, dict[str, str]] = {
    "initial": {
        "layer": "输入",
        "server_op": "—",
        "client_op": "定点加密 (ElGamal)",
        "data_form": "int32[N] → 密文 (c1, c2) 椭圆曲线点阵",
    },
    "after_conv": {
        "layer": "Conv",
        "server_op": "同态卷积 + 偏置",
        "client_op": "解密 → ReLU",
        "data_form": "密文特征图 → int32 激活图",
    },
    "after_pool": {
        "layer": "MaxPool",
        "server_op": "同态最大池化",
        "client_op": "解密 → 右移截断 (shift)",
        "data_form": "密文 → 截断后 int32 向量",
    },
    "after_fc1": {
        "layer": "FC1",
        "server_op": "同态全连接",
        "client_op": "解密 → ReLU → 右移截断",
        "data_form": "密文 → int32 隐藏层",
    },
    "after_fc2": {
        "layer": "FC2 / Logits",
        "server_op": "同态全连接",
        "client_op": "解密 → ReLU → argmax",
        "data_form": "密文 → int32 logits (10)",
    },
}


def tensor_summary(arr: np.ndarray, *, name: str = "tensor", fixed_bits: int | None = None) -> dict[str, Any]:
    flat = arr.flatten()
    out: dict[str, Any] = {
        "name": name,
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "size": int(arr.size),
    }
    if flat.size:
        first = flat[0]
        if hasattr(first, "x") and hasattr(first, "y"):
            out["element_type"] = "elliptic_curve_point"
            out["sample"] = [f"({int(first.x())}, {int(first.y())})"]
        else:
            try:
                nums = flat[: min(8, flat.size)].astype(float)
                out["sample"] = nums.tolist()
                out["min"] = float(np.min(flat.astype(float)))
                out["max"] = float(np.max(flat.astype(float)))
                out["mean"] = float(np.mean(flat.astype(float)))
            except (TypeError, ValueError):
                out["sample"] = [str(x) for x in flat[: min(4, flat.size)]]
    else:
        out["sample"] = []
    if fixed_bits is not None:
        out["fixed_point_bits"] = fixed_bits
        out["encoding"] = f"fixed-point Q{fixed_bits}"
    return out


def ciphertext_summary(
    c1: np.ndarray,
    c2: np.ndarray,
    *,
    phase_id: str,
    direction: str,
    chunks_c1: int = 0,
    chunks_c2: int = 0,
) -> dict[str, Any]:
    meta = PHASE_META.get(phase_id, {})
    return {
        "phase_id": phase_id,
        "direction": direction,
        "layer": meta.get("layer", phase_id),
        "data_form": "ElGamal 密文对 (c1, c2)，每元素为椭圆曲线点",
        "c1": tensor_summary(c1, name="c1"),
        "c2": tensor_summary(c2, name="c2"),
        "wire_chunks": {"c1": chunks_c1, "c2": chunks_c2},
    }


def make_trace_step(
    step_id: str,
    *,
    category: str,
    title: str,
    summary: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "category": category,
        "title": title,
        "summary": summary,
        "detail": detail or {},
    }


def phase_meta(phase_id: str) -> dict[str, str]:
    return PHASE_META.get(phase_id, {"layer": phase_id, "server_op": "—", "client_op": "—", "data_form": "—"})
