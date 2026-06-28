"""AHE homomorphic feasibility assessment for Network A.

Proposition (deployability)
----------------------------
Given fixed-point reference path r (``forward_fixed_point``), post-AHE inference a
(WebSocket session or homomorphic plain numpy proxy), and truncation plan π:

    deployable  ⇔  range_safe(π, weights, data)  ∧  |Acc(r) − Acc(a)| < τ

where τ defaults to ``VPIN_ACC_GAP_THRESHOLD`` (10% for HDC deploy gate).
Float-vs-fixed QAT gap is recorded as a secondary diagnostic only.

Sub-problems
------------
1. **Range / overflow** (deterministic): at each truncate checkpoint, pre-shift
   magnitude must be BSGS-decryptable; post-shift magnitude must fit int32 re-encrypt.
2. **Truncation error** (deterministic per sample): TReLU loses at most 0.5 ulp at
   target scale f=16 per shifted element.
3. **Margin / flip risk** (conservative): if float top-1 margin < error bound propagated
   to logits, fixed prediction may flip (necessary, not sufficient).
4. **Accuracy certificate** (empirical): |Acc(reference) − Acc(ahe)| < τ — final gate.

This module does not use large models; complexity is O(N · forward) on a calibration set.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch

from model_training.network_a.fixed_point import shift_bits
from model_training.network_a.model import NetworkA, _quantize_fc_weight
from model_training.network_a.truncation_config import (
    BSGS_ABS_SAFE_LIMIT,
    FIXED_POINT_BITS,
    INT32_ABS_SAFE_LIMIT,
    POOL_INV_BITS,
    ActivationStats,
    TruncationPlan,
    post_shift_magnitude,
    validate_activation_stats,
)
from vpin_client.hdc import scale_rules as sr

# Paper / implementation design reference (~35 bit decryptable layer output).
PAPER_BIT_BUDGET = 35
PAPER_ABS_LIMIT = (1 << PAPER_BIT_BUDGET) - 1

DEFAULT_ACC_TOLERANCE = sr.ACCURACY_TOLERANCE_STRICT  # 0.001 — strict parity scripts only
DEFAULT_ACC_GAP_THRESHOLD = sr.DEFAULT_ACC_GAP_THRESHOLD  # 0.10 — HDC deploy gate
# Per-element real error after shifting( from_bits → 16 ): ≤ 0.5 / 2^16.
TRUNC_ULP_REAL = 0.5 / (2**FIXED_POINT_BITS)


@dataclass
class StaticWeightBounds:
    """Weight-only magnitude bounds (independent of calibration images)."""

    fc1_w_fp_max: int
    fc1_b_fp_max: int
    fc2_w_fp_max: int
    fc2_b_fp_max: int
    # Conservative MAC upper bound assuming every pool dim equals max_pool_post_shift.
    mac_fc1_bound: int
    mac_fc2_bound: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckpointRangeReport:
    name: str
    from_bits: int
    pre_shift_max: float
    post_shift_max: float
    pre_shift_bits: int
    bsgs_ok: bool
    int32_reencrypt_ok: bool
    paper35_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TruncationBoundaryStats:
    from_bits: int
    max_lost_real: float
    mean_lost_real: float
    pct_exact: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarginRiskReport:
    """Conservative margin-based flip risk on calibration samples."""

    n_samples: int
    n_float_fixed_mismatch: int
    n_margin_below_bound: int
    logit_perturbation_bound: float
    mismatches_with_small_float_margin: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AccuracyCertificate:
    n_samples: int
    reference_acc: float
    ahe_acc: float
    acc_gap: float
    pred_mismatches: int
    pass_tolerance: bool
    tolerance: float
    ahe_mode: str
    float_fixed_gap: float | None = None
    float_acc: float | None = None
    fixed_acc: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AHEFeasibilityReport:
    """Full deployability report."""

    deployable: bool
    range_ok: bool
    accuracy_ok: bool
    plan: dict[str, Any]
    static_bounds: dict[str, Any]
    calibration: dict[str, Any]
    checkpoints: list[dict[str, Any]]
    truncation_boundaries: dict[str, Any]
    margin_risk: dict[str, Any]
    accuracy: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def static_weight_bounds(
    model: NetworkA,
    *,
    max_pool_post_shift: int,
    max_fc1_post_shift: int | None = None,
) -> StaticWeightBounds:
    """Derive FC MAC upper bounds from quantized weights and activation ceilings."""
    w1 = _quantize_fc_weight(model.fc1.weight.data.cpu().T).numpy()
    b1 = _quantize_fc_weight(model.fc1.bias.data.cpu()).numpy()
    w2 = _quantize_fc_weight(model.fc2.weight.data.cpu().T).numpy()
    b2 = _quantize_fc_weight(model.fc2.bias.data.cpu()).numpy()

    w1_max = int(np.max(np.abs(w1)))
    b1_max = int(np.max(np.abs(b1)))
    w2_max = int(np.max(np.abs(w2)))
    b2_max = int(np.max(np.abs(b2)))

    din1 = model.fc1.in_features
    din2 = model.fc2.in_features
    mac1 = din1 * max_pool_post_shift * w1_max + b1_max
    hidden_max = max_fc1_post_shift if max_fc1_post_shift is not None else int(post_shift_magnitude(float(mac1), 32))
    mac2 = din2 * hidden_max * w2_max + b2_max

    return StaticWeightBounds(
        fc1_w_fp_max=w1_max,
        fc1_b_fp_max=b1_max,
        fc2_w_fp_max=w2_max,
        fc2_b_fp_max=b2_max,
        mac_fc1_bound=mac1,
        mac_fc2_bound=mac2,
    )


def scan_activation_bounds(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    *,
    n: int = 500,
) -> ActivationStats:
    """Empirical per-checkpoint max |activation| over calibration images."""
    model.eval()
    max_pool = 0.0
    max_fc1 = 0.0
    max_fc2 = 0.0
    seen = 0
    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True)
            max_pool = max(max_pool, bounds["after_pool_pre_shift"])
            max_fc1 = max(max_fc1, bounds["after_fc1_pre_relu"])
            max_fc2 = max(max_fc2, bounds.get("after_fc2_pre_relu", 0.0))
            seen += images.size(0)

    return ActivationStats(
        n_samples=seen,
        max_after_pool_pre_shift=max_pool,
        max_after_fc1_pre_relu=max_fc1,
        max_after_fc2_pre_relu=max_fc2,
        max_post_pool_shift=post_shift_magnitude(max_pool, model.plan.shift_pool),
        max_post_fc1_shift=post_shift_magnitude(max_fc1, model.plan.shift_fc1),
    )


def _checkpoint_reports(stats: ActivationStats, plan: TruncationPlan) -> list[CheckpointRangeReport]:
    rows: list[CheckpointRangeReport] = []

    def _row(name: str, from_bits: int, pre_max: float) -> None:
        post = post_shift_magnitude(pre_max, from_bits)
        pre_i = int(pre_max)
        rows.append(
            CheckpointRangeReport(
                name=name,
                from_bits=from_bits,
                pre_shift_max=pre_max,
                post_shift_max=post,
                pre_shift_bits=pre_i.bit_length() if pre_i > 0 else 0,
                bsgs_ok=pre_max < BSGS_ABS_SAFE_LIMIT,
                int32_reencrypt_ok=post < INT32_ABS_SAFE_LIMIT,
                paper35_ok=pre_max < PAPER_ABS_LIMIT,
            )
        )

    _row("after_pool", plan.shift_pool, stats.max_after_pool_pre_shift)
    _row("after_fc1", plan.shift_fc1, stats.max_after_fc1_pre_relu)
    # FC2: no client shift in Network A; pre-relu is f=32 and only needs BSGS.
    pre_fc2 = stats.max_after_fc2_pre_relu
    rows.append(
        CheckpointRangeReport(
            name="after_fc2",
            from_bits=FIXED_POINT_BITS * 2,
            pre_shift_max=pre_fc2,
            post_shift_max=pre_fc2,
            pre_shift_bits=int(pre_fc2).bit_length() if pre_fc2 > 0 else 0,
            bsgs_ok=pre_fc2 < BSGS_ABS_SAFE_LIMIT,
            int32_reencrypt_ok=True,
            paper35_ok=pre_fc2 < PAPER_ABS_LIMIT,
        )
    )
    return rows


def _truncation_boundary_stats(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    plan: TruncationPlan,
    *,
    n: int = 200,
) -> dict[str, TruncationBoundaryStats]:
    """Per-boundary truncation loss when applying TReLU shift (real units)."""
    model.eval()
    pool_losses: list[float] = []
    fc1_losses: list[float] = []
    pool_exact = 0
    fc1_exact = 0
    pool_total = 0
    fc1_total = 0
    seen = 0

    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            _, bounds = model.forward_fixed_point(images, return_bounds=True, plan=plan)
            # Pool: approximate from bounds — compare shift round-trip on scalar max
            pre_pool = bounds["after_pool_pre_shift"]
            if pre_pool > 0:
                t = torch.tensor([pre_pool], dtype=torch.int64)
                shifted = shift_bits(t, plan.shift_pool)
                back_real = shifted.float().item() / (2**FIXED_POINT_BITS)
                orig_real = pre_pool / (2**plan.shift_pool)
                pool_losses.append(abs(orig_real - back_real))
                pool_total += 1
                if pool_losses[-1] == 0:
                    pool_exact += 1

            pre_fc1 = bounds["after_fc1_pre_relu"]
            if pre_fc1 > 0:
                t = torch.tensor([pre_fc1], dtype=torch.int64)
                shifted = shift_bits(torch.clamp(t, min=0), plan.shift_fc1)
                back_real = shifted.float().item() / (2**FIXED_POINT_BITS)
                orig_real = pre_fc1 / (2**plan.shift_fc1)
                fc1_losses.append(abs(orig_real - back_real))
                fc1_total += 1
                if fc1_losses[-1] == 0:
                    fc1_exact += 1
            seen += images.size(0)

    def _summarize(losses: list[float], exact: int, total: int, from_bits: int) -> TruncationBoundaryStats:
        if not losses:
            return TruncationBoundaryStats(from_bits, 0.0, 0.0, 100.0)
        return TruncationBoundaryStats(
            from_bits=from_bits,
            max_lost_real=float(max(losses)),
            mean_lost_real=float(np.mean(losses)),
            pct_exact=100.0 * exact / max(total, 1),
        )

    return {
        "shift_pool": _summarize(pool_losses, pool_exact, pool_total, plan.shift_pool),
        "shift_fc1": _summarize(fc1_losses, fc1_exact, fc1_total, plan.shift_fc1),
    }


def _logit_perturbation_bound(model: NetworkA, *, n_pool: int = 64, n_fc1: int = 16) -> float:
    """Conservative ‖Δlogits‖∞ bound from per-element TReLU ulp (triangle inequality, real weights)."""
    w1 = model.fc1.weight.data.cpu().numpy().T  # (64, 16)
    w2 = model.fc2.weight.data.cpu().numpy().T  # (16, 10)
    row_l1_fc1 = float(np.max(np.sum(np.abs(w1), axis=0)))
    row_l1_fc2 = float(np.max(np.sum(np.abs(w2), axis=1)))
    ulp = TRUNC_ULP_REAL
    bound_pool = n_pool * ulp * row_l1_fc1 * row_l1_fc2
    bound_fc1 = n_fc1 * ulp * row_l1_fc2
    return bound_pool + bound_fc1


def _float_margin(logits: np.ndarray) -> float:
    if logits.size < 2:
        return float("inf")
    top2 = np.partition(logits.astype(np.float64), -2)[-2:]
    return float(top2[1] - top2[0])


def margin_flip_risk(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    *,
    n: int = 1000,
) -> MarginRiskReport:
    model.eval()
    perturb_bound = _logit_perturbation_bound(model)
    n_mismatch = 0
    n_margin_low = 0
    n_mismatch_small_margin = 0
    seen = 0

    with torch.no_grad():
        for images, _ in loader:
            if seen >= n:
                break
            images = images.to(device)
            fl = model.forward_float(images).cpu().numpy()
            gl = model.forward_fixed_point(images).cpu().numpy()
            for i in range(fl.shape[0]):
                pf = int(fl[i].argmax())
                pg = int(gl[i].argmax())
                margin = _float_margin(fl[i])
                if pf != pg:
                    n_mismatch += 1
                    if margin < 2 * perturb_bound:
                        n_mismatch_small_margin += 1
                if margin < perturb_bound:
                    n_margin_low += 1
            seen += images.size(0)

    return MarginRiskReport(
        n_samples=seen,
        n_float_fixed_mismatch=n_mismatch,
        n_margin_below_bound=n_margin_low,
        logit_perturbation_bound=perturb_bound,
        mismatches_with_small_float_margin=n_mismatch_small_margin,
    )


def certificate_float_fixed_diagnostic(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    *,
    n: int | None = None,
) -> dict[str, Any]:
    """Secondary QAT diagnostic: float vs fixed training-path accuracy (not deploy gate)."""
    model.eval()
    float_correct = fixed_correct = mismatches = total = seen = 0
    with torch.no_grad():
        for images, labels in loader:
            if n is not None and seen >= n:
                break
            images = images.to(device)
            labels = labels.to(device)
            pf = model.forward_float(images).argmax(dim=1)
            pg = model.forward_fixed_point(images).argmax(dim=1)
            float_correct += (pf == labels).sum().item()
            fixed_correct += (pg == labels).sum().item()
            mismatches += (pf != pg).sum().item()
            total += labels.size(0)
            seen += images.size(0)
    float_acc = float_correct / max(total, 1)
    fixed_acc = fixed_correct / max(total, 1)
    return {
        "n_samples": total,
        "float_acc": float_acc,
        "fixed_acc": fixed_acc,
        "float_fixed_gap": abs(float_acc - fixed_acc),
        "pred_mismatches": mismatches,
        "diagnostic_only": True,
    }


async def _certificate_ahe_accuracy_async(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    *,
    weights: Any,
    plan: TruncationPlan,
    tolerance: float,
    model_id: str,
    backend: str,
    n: int | None = None,
    try_websocket: bool = True,
) -> tuple[AccuracyCertificate, list[str]]:
    """Primary deploy gate: reference (fixed-point) vs post-AHE inference accuracy."""
    from model_training.network_a.evaluate import _numpy_homomorphic_plain
    from model_training.network_a.preprocess import preprocess_batch_uint8
    from vpin_client.data.preprocess import load_mnist_test

    model.eval()
    ref_correct = ahe_correct = pred_mismatches = total = 0
    warnings: list[str] = []
    use_ws = False

    async def _ws_one(i: int) -> tuple[int, int, int, int]:
        prep = load_mnist_test(i)
        label = prep.label
        if label is None:
            raise IndexError("no label")
        images = torch.from_numpy(prep.raw_uint8).unsqueeze(0).unsqueeze(0).to(device)
        with torch.no_grad():
            ref_pred = int(model.forward_fixed_point(images, plan=plan).argmax(dim=1).item())
        from vpin_client.protocol.ws_ahe_client import run_ahe_session

        result = await run_ahe_session(
            backend,
            model_id,
            prep.fixed_int32,
            mnist_index=i,
            label=label,
            preprocess_ms=0.0,
        )
        ahe_pred = result.prediction
        return ref_pred, ahe_pred, label, int(ref_pred != ahe_pred)

    if try_websocket and backend:
        try:
            ref_pred, ahe_pred, label, mismatch = await asyncio.wait_for(_ws_one(0), timeout=5.0)
            use_ws = True
            if ref_pred == label:
                ref_correct += 1
            if ahe_pred == label:
                ahe_correct += 1
            if mismatch:
                pred_mismatches += 1
            total += 1
            limit = n if n is not None else 10_000
            for i in range(1, limit):
                try:
                    ref_pred, ahe_pred, label, mismatch = await _ws_one(i)
                except IndexError:
                    break
                if ref_pred == label:
                    ref_correct += 1
                if ahe_pred == label:
                    ahe_correct += 1
                if mismatch:
                    pred_mismatches += 1
                total += 1
        except Exception as exc:
            use_ws = False
            warnings.append(
                f"AHE WebSocket backend unavailable ({exc}); using plain_homomorphic_proxy"
            )

    if not use_ws:
        seen = 0
        with torch.no_grad():
            for images, labels in loader:
                if n is not None and seen >= n:
                    break
                images = images.to(device)
                labels = labels.to(device)
                ref_preds = model.forward_fixed_point(images, plan=plan).argmax(dim=1)
                for b in range(images.size(0)):
                    if n is not None and seen >= n:
                        break
                    img = images[b : b + 1]
                    _, fixed_batch = preprocess_batch_uint8(img.cpu())
                    np_out = _numpy_homomorphic_plain(
                        fixed_batch[0, 0].numpy().astype(np.int64), weights, plan
                    )
                    proxy_logits = np_out["after_fc2"].reshape(-1)
                    ahe_pred = int(proxy_logits.argmax())
                    ref_pred = int(ref_preds[b].item())
                    label = int(labels[b].item())
                    if ref_pred == label:
                        ref_correct += 1
                    if ahe_pred == label:
                        ahe_correct += 1
                    if ref_pred != ahe_pred:
                        pred_mismatches += 1
                    total += 1
                    seen += 1

    reference_acc = ref_correct / max(total, 1)
    ahe_acc = ahe_correct / max(total, 1)
    acc_gap = abs(reference_acc - ahe_acc)
    cert = AccuracyCertificate(
        n_samples=total,
        reference_acc=reference_acc,
        ahe_acc=ahe_acc,
        acc_gap=acc_gap,
        pred_mismatches=pred_mismatches,
        pass_tolerance=acc_gap < tolerance,
        tolerance=tolerance,
        ahe_mode="websocket" if use_ws else "plain_homomorphic_proxy",
    )
    return cert, warnings


def certificate_ahe_accuracy(
    model: NetworkA,
    loader: Iterable,
    device: torch.device,
    *,
    weights: Any,
    plan: TruncationPlan,
    tolerance: float = DEFAULT_ACC_GAP_THRESHOLD,
    model_id: str = "cnn-mnist-trained",
    backend: str = "ws://127.0.0.1:8000/api/v1/session/ws",
    n: int | None = 1000,
    try_websocket: bool = True,
) -> tuple[AccuracyCertificate, list[str]]:
    import asyncio

    return asyncio.run(
        _certificate_ahe_accuracy_async(
            model,
            loader,
            device,
            weights=weights,
            plan=plan,
            tolerance=tolerance,
            model_id=model_id,
            backend=backend,
            n=n,
            try_websocket=try_websocket,
        )
    )


def _model_weights(model: NetworkA) -> Any:
    from vpin_backend.inference.homomorphic_network_a import NetworkAWeights

    return NetworkAWeights(
        weight_fc1=model.fc1.weight.detach().cpu().numpy().T.astype(np.float64),
        bias_fc1=model.fc1.bias.detach().cpu().numpy().astype(np.float64),
        weight_fc2=model.fc2.weight.detach().cpu().numpy().T.astype(np.float64),
        bias_fc2=model.fc2.bias.detach().cpu().numpy().astype(np.float64),
    )


def assess_ahe_feasibility(
    model: NetworkA,
    train_loader: Iterable,
    test_loader: Iterable,
    device: torch.device,
    *,
    plan: TruncationPlan | None = None,
    cal_n: int = 500,
    margin_n: int = 1000,
    acc_tolerance: float | None = None,
    acc_gap_threshold: float | None = None,
    ahe_n: int = 1000,
    model_id: str = "cnn-mnist-trained",
    ahe_backend: str = "ws://127.0.0.1:8000/api/v1/session/ws",
    try_websocket: bool = True,
) -> AHEFeasibilityReport:
    """Run full feasibility pipeline and return deployability verdict."""
    tau = acc_gap_threshold if acc_gap_threshold is not None else (
        acc_tolerance if acc_tolerance is not None else DEFAULT_ACC_GAP_THRESHOLD
    )
    plan = plan or model.plan
    model.plan = plan
    errors: list[str] = []
    warnings: list[str] = []

    stats = scan_activation_bounds(model, train_loader, device, n=cal_n)
    ok_stats, stat_errs = validate_activation_stats(stats, plan)
    if not ok_stats:
        errors.extend(stat_errs)

    checkpoints = _checkpoint_reports(stats, plan)
    for cp in checkpoints:
        if not cp.bsgs_ok:
            errors.append(
                f"{cp.name}: pre-shift max {cp.pre_shift_max:.3e} (≈2^{cp.pre_shift_bits}) "
                f"exceeds BSGS limit {BSGS_ABS_SAFE_LIMIT:.3e}"
            )
        if cp.name != "after_fc2" and not cp.int32_reencrypt_ok:
            errors.append(
                f"{cp.name}: post-shift max {cp.post_shift_max:.3e} exceeds int32 re-encrypt limit"
            )
        if not cp.paper35_ok:
            warnings.append(
                f"{cp.name}: pre-shift max exceeds paper ~{PAPER_BIT_BUDGET}-bit budget "
                f"({PAPER_ABS_LIMIT:.3e}) — may stress decrypt latency"
            )

    post_pool_int = max(1, int(stats.max_post_pool_shift))
    post_fc1_int = max(1, int(stats.max_post_fc1_shift))
    static = static_weight_bounds(
        model,
        max_pool_post_shift=post_pool_int,
        max_fc1_post_shift=post_fc1_int,
    )
    if static.mac_fc1_bound > BSGS_ABS_SAFE_LIMIT:
        warnings.append(
            f"static MAC FC1 bound {static.mac_fc1_bound:.3e} exceeds BSGS (loose weight-only estimate)"
        )

    trunc_bounds = _truncation_boundary_stats(model, train_loader, device, plan, n=min(cal_n, 200))
    margin = margin_flip_risk(model, test_loader, device, n=margin_n)
    float_fixed = certificate_float_fixed_diagnostic(model, test_loader, device, n=ahe_n)
    accuracy_cert, ahe_warnings = certificate_ahe_accuracy(
        model,
        test_loader,
        device,
        weights=_model_weights(model),
        plan=plan,
        tolerance=tau,
        model_id=model_id,
        backend=ahe_backend,
        n=ahe_n,
        try_websocket=try_websocket,
    )
    warnings.extend(ahe_warnings)
    accuracy_dict = accuracy_cert.to_dict()
    accuracy_dict["float_fixed_diagnostic"] = float_fixed

    if not accuracy_cert.pass_tolerance:
        errors.append(
            f"post-AHE accuracy gap {accuracy_cert.acc_gap:.4f} ≥ tolerance {tau} "
            f"(reference={accuracy_cert.reference_acc:.4f}, ahe={accuracy_cert.ahe_acc:.4f}, "
            f"ahe_mode={accuracy_cert.ahe_mode}, pred_mismatches={accuracy_cert.pred_mismatches})"
        )

    if margin.n_float_fixed_mismatch > 0 and margin.n_float_fixed_mismatch == margin.mismatches_with_small_float_margin:
        warnings.append(
            "all float/fixed pred mismatches occur with small float margin — consistent with truncation"
        )

    range_ok = ok_stats and all(cp.bsgs_ok for cp in checkpoints) and all(
        cp.int32_reencrypt_ok for cp in checkpoints if cp.name != "after_fc2"
    )

    return AHEFeasibilityReport(
        deployable=range_ok and accuracy_cert.pass_tolerance and len(errors) == 0,
        range_ok=range_ok,
        accuracy_ok=accuracy_cert.pass_tolerance,
        plan=plan.to_dict(),
        static_bounds=static.to_dict(),
        calibration=stats.to_dict(),
        checkpoints=[c.to_dict() for c in checkpoints],
        truncation_boundaries={k: v.to_dict() for k, v in trunc_bounds.items()},
        margin_risk=margin.to_dict(),
        accuracy=accuracy_dict,
        errors=errors,
        warnings=warnings,
    )
