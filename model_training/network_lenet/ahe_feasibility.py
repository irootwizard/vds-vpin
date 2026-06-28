"""HDC feasibility / Compile for LeNet-CIFAR (§6–§8).

Scans a calibration set for per-checkpoint pre-shift magnitudes, certifies
post-AHE (homomorphic plain proxy until P4 WS) vs fixed-point reference accuracy,
then produces the HomomorphicDeployPlan (``homomorphic_deploy_plan.json``):

    deployable ⇔ range_ok ∧ accuracy_ok

where ``accuracy_ok`` uses |Acc(reference) − Acc(ahe_proxy)| < τ (default 10%).
Float-vs-fixed gap is a secondary QAT diagnostic only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import torch
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-client"))

from model_training.network_lenet.fixed_point import apply_client_action
from model_training.network_lenet.model import LeNetCIFAR, _quantize
from model_training.network_lenet.preprocess import preprocess_batch_rgb
from model_training.network_lenet.truncation_config import (
    ActivationStats,
    TruncationPlan,
)
from vpin_client.hdc import scale_rules as sr
from vpin_client.hdc.compile_deploy_plan import HomomorphicDeployPlan, compile_deploy_plan
from vpin_client.hdc.model_decomposer import build_layer_graph

ACC_TOLERANCE = sr.DEFAULT_ACC_GAP_THRESHOLD
_SCALE = 2**16


def scan_activation_bounds(
    model: LeNetCIFAR, loader: Iterable, device: torch.device, *, n: int = 500
) -> ActivationStats:
    model.eval()
    stats = ActivationStats()
    seen = 0
    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True)
            stats.max_after_conv1 = max(stats.max_after_conv1, bounds.get("after_conv1_pre_relu", bounds.get("after_conv1", 0.0)))
            stats.max_after_pool1_pre_shift = max(stats.max_after_pool1_pre_shift, bounds.get("after_pool1_pre_shift", bounds.get("after_pool1", 0.0)))
            stats.max_after_conv2 = max(stats.max_after_conv2, bounds.get("after_conv2_pre_relu", bounds.get("after_conv2", 0.0)))
            stats.max_after_pool2_pre_shift = max(stats.max_after_pool2_pre_shift, bounds.get("after_pool2_pre_shift", bounds.get("after_pool2", 0.0)))
            stats.max_after_fc1_pre_relu = max(stats.max_after_fc1_pre_relu, bounds.get("after_fc1_pre_relu", bounds.get("after_fc1", 0.0)))
            stats.max_after_fc2_pre_relu = max(stats.max_after_fc2_pre_relu, bounds.get("after_fc2_pre_relu", bounds.get("after_fc2", 0.0)))
            seen += images.size(0)
    stats.n_samples = seen
    return stats


def _homomorphic_plain_conv(x_int: torch.Tensor, conv) -> torch.Tensor:
    w_q = _quantize(conv.weight.detach().cpu())
    acc = F.conv2d(x_int.double().cpu(), w_q)
    acc = torch.trunc(acc)
    out = torch.div(acc, _SCALE, rounding_mode="floor")
    b_q = _quantize(conv.bias.detach().cpu())
    return (out + b_q.view(1, -1, 1, 1)).to(torch.int64)


def _homomorphic_plain_pool(x_int: torch.Tensor, inv_fp: int, k: int) -> torch.Tensor:
    summed = torch.trunc(F.avg_pool2d(x_int.double(), kernel_size=k, stride=k) * (k * k))
    return summed.to(torch.int64) * inv_fp


def _homomorphic_plain_fc(x_int: torch.Tensor, linear) -> torch.Tensor:
    w = _quantize(linear.weight.detach().cpu().T).to(torch.int64)
    b = _quantize(linear.bias.detach().cpu()).to(torch.int64)
    return x_int.to(torch.int64).cpu() @ w + b


def homomorphic_plain_logits(
    model: LeNetCIFAR, images: torch.Tensor, *, plan: TruncationPlan
) -> torch.Tensor:
    """Homomorphic plain proxy (no WS until P4) — independent integer execution path."""
    _, fixed = preprocess_batch_rgb(images.cpu())
    k = plan.pool_k
    inv_fp = plan.pool_inv_fp

    c1 = _homomorphic_plain_conv(fixed, model.conv1)
    after_conv1 = apply_client_action(c1, "relu")
    p1 = _homomorphic_plain_pool(after_conv1, inv_fp, k)
    s1 = apply_client_action(p1, "shift", shift_bits_val=plan.shift_pool)

    c2 = _homomorphic_plain_conv(s1, model.conv2)
    after_conv2 = apply_client_action(c2, "relu")
    p2 = _homomorphic_plain_pool(after_conv2, inv_fp, k)
    s2 = apply_client_action(p2, "shift", shift_bits_val=plan.shift_pool)
    flat = s2.reshape(s2.shape[0], -1)

    h1 = _homomorphic_plain_fc(flat, model.fc1)
    after_fc1 = apply_client_action(h1, "relu_then_shift", shift_bits_val=plan.shift_fc)
    h2 = _homomorphic_plain_fc(after_fc1, model.fc2)
    after_fc2 = apply_client_action(h2, "relu_then_shift", shift_bits_val=plan.shift_fc)
    return _homomorphic_plain_fc(after_fc2, model.fc3)


def certificate_float_fixed_diagnostic(
    model: LeNetCIFAR,
    loader: Iterable,
    device: torch.device,
    *,
    n: int | None = None,
) -> dict:
    """Secondary QAT diagnostic: float vs fixed (not deploy gate)."""
    model.eval()
    float_correct = fixed_correct = mismatches = total = seen = 0
    with torch.no_grad():
        for images, labels in loader:
            if n is not None and seen >= n:
                break
            images = images.to(device)
            labels = labels.to(device)
            pf = model.forward_float(images).argmax(dim=1).to(labels.device)
            pg = model.forward_fixed_point(images).argmax(dim=1).to(labels.device)
            float_correct += (pf == labels).sum().item()
            fixed_correct += (pg == labels).sum().item()
            mismatches += (pf != pg).sum().item()
            total += labels.size(0)
            seen += images.size(0)
    total = max(total, 1)
    fa = float_correct / total
    ga = fixed_correct / total
    return {
        "n_samples": total,
        "float_acc": fa,
        "fixed_acc": ga,
        "float_fixed_gap": abs(fa - ga),
        "pred_mismatches": mismatches,
        "diagnostic_only": True,
    }


def certificate_ahe_accuracy(
    model: LeNetCIFAR,
    loader: Iterable,
    device: torch.device,
    *,
    tolerance: float = ACC_TOLERANCE,
    n: int | None = None,
    plan: TruncationPlan | None = None,
) -> dict:
    """Primary deploy gate: fixed-point reference vs homomorphic plain proxy."""
    plan = plan or model.plan
    model.eval()
    ref_correct = ahe_correct = pred_mismatches = total = seen = 0
    with torch.no_grad():
        for images, labels in loader:
            if n is not None and seen >= n:
                break
            images = images.to(device)
            labels = labels.to(device)
            ref_preds = model.forward_fixed_point(images, plan=plan).argmax(dim=1)
            proxy_logits = homomorphic_plain_logits(model, images, plan=plan)
            ahe_preds = proxy_logits.argmax(dim=1).to(labels.device)
            ref_correct += (ref_preds == labels).sum().item()
            ahe_correct += (ahe_preds == labels).sum().item()
            pred_mismatches += (ref_preds != ahe_preds).sum().item()
            total += labels.size(0)
            seen += images.size(0)
    total = max(total, 1)
    reference_acc = ref_correct / total
    ahe_acc = ahe_correct / total
    acc_gap = abs(reference_acc - ahe_acc)
    return {
        "n_samples": total,
        "reference_acc": reference_acc,
        "ahe_acc": ahe_acc,
        "acc_gap": acc_gap,
        "pred_mismatches": pred_mismatches,
        "tolerance": tolerance,
        "ok": acc_gap < tolerance,
        "ahe_mode": "plain_homomorphic_proxy",
    }


def compile_lenet_plan(
    model: LeNetCIFAR,
    train_loader: Iterable,
    test_loader: Iterable,
    device: torch.device,
    *,
    plan: TruncationPlan | None = None,
    cal_n: int = 500,
    acc_n: int | None = 2000,
    acc_gap_threshold: float | None = None,
) -> HomomorphicDeployPlan:
    plan = plan or model.plan
    model.plan = plan
    stats = scan_activation_bounds(model, train_loader, device, n=cal_n)
    tau = acc_gap_threshold if acc_gap_threshold is not None else ACC_TOLERANCE
    accuracy = certificate_ahe_accuracy(
        model, test_loader, device, tolerance=tau, n=acc_n, plan=plan
    )
    float_fixed = certificate_float_fixed_diagnostic(model, test_loader, device, n=acc_n)
    accuracy["float_fixed_diagnostic"] = float_fixed

    graph = build_layer_graph("lenet_cifar")
    deploy = compile_deploy_plan(
        model_id="lenet-cifar10",
        graph=graph,
        m_pre_table=stats.m_pre_table(),
        accuracy=accuracy,
        acc_gap_threshold=tau,
        calibration={"stats": stats.to_dict(), "cal_n": stats.n_samples},
    )
    return deploy


def assess_and_write(
    model: LeNetCIFAR,
    train_loader: Iterable,
    test_loader: Iterable,
    device: torch.device,
    out_path: Path,
    *,
    plan: TruncationPlan | None = None,
    cal_n: int = 500,
    acc_n: int | None = 2000,
    acc_gap_threshold: float | None = None,
) -> HomomorphicDeployPlan:
    deploy = compile_lenet_plan(
        model,
        train_loader,
        test_loader,
        device,
        plan=plan,
        cal_n=cal_n,
        acc_n=acc_n,
        acc_gap_threshold=acc_gap_threshold,
    )
    deploy.save(out_path)
    return deploy
