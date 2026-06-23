#!/usr/bin/env python3
"""Per-image layerwise float vs fixed-point diagnostic for Network A."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-backend"))

from model_training.network_a.fixed_point import apply_client_action, shift_bits
from model_training.network_a.model import NetworkA, _fc_matmul, _pool_fixed, _quantize_fc_weight
from model_training.network_a.preprocess import preprocess_batch_uint8, uint8_to_float_input
from model_training.network_a.truncation_config import FIXED_POINT_BITS, plan_from_topology
from vpin_client.data.preprocess import load_mnist_test


def _layer_stats(name: str, float_t: torch.Tensor, fixed_t: torch.Tensor, scale: float) -> dict:
    """Compare tensors in real units (divide fixed by 2^scale)."""
    f = float_t.detach().float().flatten().cpu().numpy()
    x = fixed_t.detach().float().flatten().cpu().numpy() / (2.0**scale)
    if f.shape != x.shape:
        return {"layer": name, "error": f"shape mismatch {f.shape} vs {x.shape}"}
    diff = f - x
    abs_diff = np.abs(diff)
    rel = abs_diff / (np.abs(f) + 1e-8)
    return {
        "layer": name,
        "float_scale": "real",
        "fixed_scale_bits": scale,
        "max_abs_diff": float(abs_diff.max()),
        "mean_abs_diff": float(abs_diff.mean()),
        "max_rel_err": float(rel.max()),
        "mean_rel_err": float(rel.mean()),
        "float_max": float(np.abs(f).max()),
        "fixed_max_real": float(np.abs(x).max()),
        "n_zeros_float": int((f == 0).sum()),
        "n_zeros_fixed": int((x == 0).sum()),
        "sign_agree_pct": float((np.sign(f) == np.sign(x)).mean() * 100),
    }


def float_intermediates(model: NetworkA, images: torch.Tensor) -> dict[str, torch.Tensor]:
    x = uint8_to_float_input(images)
    x = model._conv(x)
    after_conv = F.relu(x)
    pooled_sum = F.avg_pool2d(after_conv, kernel_size=4, stride=4) * 16.0
    flat = pooled_sum.reshape(1, -1) / 16.0
    pooled_pre_shift_real = pooled_sum  # int path uses sum*inv_fp; float equiv magnitude ~f26
    fc1_pre = model.fc1(flat)
    after_fc1 = F.relu(fc1_pre)
    fc2_pre = model.fc2(after_fc1)
    return {
        "after_conv": after_conv,
        "after_pool_pre_shift": pooled_sum,
        "after_pool": flat,
        "after_fc1_pre_relu": fc1_pre,
        "after_fc1": after_fc1,
        "after_fc2_pre_relu": fc2_pre,
        "logits": fc2_pre,
    }


def fixed_intermediates_detailed(model: NetworkA, images: torch.Tensor, plan) -> dict[str, torch.Tensor]:
    _, fixed_in = preprocess_batch_uint8(images.cpu())
    x = model._conv_fixed_int(fixed_in)
    after_conv = apply_client_action(x, "relu")
    pool_pre = _pool_fixed(after_conv, plan.pool_inv_fp)
    pool_post = apply_client_action(pool_pre, "shift", shift_bits_val=plan.shift_pool)
    after_pool = pool_post.reshape(1, -1)
    fc1_pre = _fc_matmul(after_pool, model.fc1.weight.data.cpu(), model.fc1.bias.data.cpu())
    after_fc1 = apply_client_action(fc1_pre, "relu_then_shift", shift_bits_val=plan.shift_fc1)
    fc2_pre = _fc_matmul(after_fc1, model.fc2.weight.data.cpu(), model.fc2.bias.data.cpu())
    after_fc2 = apply_client_action(fc2_pre, "relu_only")
    return {
        "input_fixed": fixed_in,
        "after_conv": after_conv,
        "after_pool_pre_shift": pool_pre,
        "after_pool": after_pool,
        "after_fc1_pre_relu": fc1_pre,
        "after_fc1": after_fc1,
        "after_fc2_pre_relu": fc2_pre,
        "logits": after_fc2.float() / (2**FIXED_POINT_BITS),
    }


def truncation_loss_at_shift(x_int: torch.Tensor, from_bits: int) -> dict:
    """Bits discarded by shifting(from_bits -> 16)."""
    x = x_int.detach().cpu().float()
    reals = x / (2.0**from_bits)
    scaled = reals * (2.0**16)
    truncated = scaled.to(torch.int32).float()
    lost = scaled - truncated
    return {
        "from_bits": from_bits,
        "max_lost_real": float((lost / (2.0**16)).abs().max()),
        "mean_lost_real": float((lost / (2.0**16)).abs().mean()),
        "pct_exact": float((lost == 0).float().mean() * 100),
    }


def weight_quant_error(model: NetworkA) -> dict:
    out = {}
    for name, linear in [("fc1", model.fc1), ("fc2", model.fc2)]:
        wf = linear.weight.detach().float()  # (out, in)
        wq = (_quantize_fc_weight(linear.weight.data).float() / (2**16))
        err = (wf - wq).abs()
        out[name] = {
            "shape": list(wf.shape),
            "max_abs_err": float(err.max()),
            "mean_abs_err": float(err.mean()),
            "max_rel_err": float((err / (wf.abs() + 1e-8)).max()),
        }
    return out


def diagnose_one(model: NetworkA, index: int, plan) -> dict:
    prep = load_mnist_test(index)
    img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
    label = prep.label

    with torch.no_grad():
        fl = float_intermediates(model, img)
        fx = fixed_intermediates_detailed(model, img, plan)
        pred_f = int(model.forward_float(img).argmax().item())
        pred_x = int(model.forward_fixed_point(img, plan=plan).argmax().item())

    _, fixed_in = preprocess_batch_uint8(img)
    norm_f, _ = preprocess_batch_uint8(img)

    comparisons = [
        _layer_stats("input (norm×2^16 vs fixed)", norm_f * (2**16), fixed_in, 16),
        _layer_stats("after_conv relu", fl["after_conv"], fx["after_conv"], 16),
        _layer_stats("after_pool PRE shift", fl["after_pool_pre_shift"], fx["after_pool_pre_shift"], 26),
        _layer_stats("after_pool POST shift (→f16)", fl["after_pool"], fx["after_pool"], 16),
        _layer_stats("after_fc1 PRE relu", fl["after_fc1_pre_relu"], fx["after_fc1_pre_relu"], 32),
        _layer_stats("after_fc1 POST relu+shift", fl["after_fc1"], fx["after_fc1"], 16),
        _layer_stats("logits", fl["logits"], fx["logits"], 0),
    ]

    trunc = {
        "shift_pool": truncation_loss_at_shift(fx["after_pool_pre_shift"], plan.shift_pool),
        "shift_fc1": truncation_loss_at_shift(fx["after_fc1_pre_relu"], plan.shift_fc1),
    }

    # Cumulative: float path emulated through fixed ops on float-scaled tensors
    return {
        "index": index,
        "label": label,
        "pred_float": pred_f,
        "pred_fixed": pred_x,
        "float_correct": pred_f == label,
        "fixed_correct": pred_x == label,
        "layer_compare": comparisons,
        "truncation_at_boundaries": trunc,
    }


def main() -> int:
    run_dir = REPO / "model_training" / "outputs" / "20260622_184254"
    ckpt = torch.load(run_dir / "checkpoint.pt", map_location="cpu", weights_only=False)
    plan = plan_from_topology()
    model = NetworkA(plan=plan)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    wq = weight_quant_error(model)

    # Pick: index 0 (often wrong), and first float-correct in 0..99
    indices = [0]
    for i in range(100):
        prep = load_mnist_test(i)
        img = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            pf = int(model.forward_float(img).argmax())
            px = int(model.forward_fixed_point(img, plan=plan).argmax())
        if pf == prep.label and px != prep.label:
            indices.append(i)
            break

    reports = [diagnose_one(model, idx, plan) for idx in indices]
    out = {"weight_quant": wq, "samples": reports}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
