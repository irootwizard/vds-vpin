"""LeNet-CIFAR — topology aligned with HDC homomorphic inference (lenet_cifar family).

Conv2d(3,6,5) → ReLU → sum_pool 2×2 → Conv2d(6,16,5) → ReLU → sum_pool 2×2 →
FC 400→120 → ReLU → FC 120→84 → ReLU → FC 84→10.

Fixed-point scale handling (§11.4 / §11.5):
- conv folds an internal rescale (acc f=32 → floor /2^F → f=16) so each conv ReLU
  checkpoint (π1/π3) sees f=16, exactly as the formula table demands. (Network A
  avoided this by using a fixed integer kernel; LeNet has trainable conv weights.)
- sum_pool: sum over 2×2 then ×inv_fp (=2^inv_bits=1024) → f=28; client shift 28→16.
- FC: int64 matmul x(f16)·Ŵ(f16) → f=32; client relu_then_shift 32→16 (legacy bias
  added at f16, matching the homomorphic FC layer).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from model_training.network_lenet.fixed_point import apply_client_action
from model_training.network_lenet.preprocess import preprocess_batch_rgb, rgb_to_float_input
from model_training.network_lenet.truncation_config import (
    DEFAULT_PLAN,
    FIXED_POINT_BITS,
    TruncationPlan,
)

_SCALE = 2**FIXED_POINT_BITS


def _quantize(x: torch.Tensor, bits: int = FIXED_POINT_BITS) -> torch.Tensor:
    """Truncate-toward-zero fixed-point quantization (matches real_to_fixed_point)."""
    return torch.trunc(x.to(torch.float64) * (2**bits))


def _ste_truncate_toward_zero(x: torch.Tensor) -> torch.Tensor:
    truncated = torch.trunc(x)
    return x + (truncated - x).detach()


def _ste_shift_bits(x: torch.Tensor, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> torch.Tensor:
    reals = x.float() / (2.0**from_bits)
    return _ste_truncate_toward_zero(reals * (2.0**to_bits))


class LeNetCIFAR(nn.Module):
    """LeNet-CIFAR10 with homomorphic-aligned sum pool.

    model_id:       lenet-cifar10
    network_family: lenet_cifar
    dataset:        cifar10
    """

    MODEL_ID = "lenet-cifar10"
    NETWORK_FAMILY = "lenet_cifar"
    DATASET = "cifar10"

    def __init__(self, plan: TruncationPlan | None = None) -> None:
        super().__init__()
        self.plan = plan or DEFAULT_PLAN
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(400, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def trainable_parameters(self):
        return list(self.parameters())

    # ---- float reference path ------------------------------------------------
    def forward_float(self, images: torch.Tensor) -> torch.Tensor:
        x = rgb_to_float_input(images)
        x = F.relu(self.conv1(x))
        x = F.avg_pool2d(x, 2)  # mean pool — matches fixed sum-pool/ inv_fp semantics
        x = F.relu(self.conv2(x))
        x = F.avg_pool2d(x, 2)
        x = x.reshape(x.shape[0], -1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)

    # ---- exact integer fixed-point path -------------------------------------
    def _conv_fixed_int(self, x_int: torch.Tensor, conv: nn.Conv2d) -> torch.Tensor:
        """Integer conv with internal rescale to f=16 (double accumulator for exactness)."""
        w_q = _quantize(conv.weight.detach().cpu())  # f=16
        acc = F.conv2d(x_int.double().cpu(), w_q)  # f=32, exact in float64
        acc = torch.trunc(acc)
        out = torch.div(acc, _SCALE, rounding_mode="floor")  # back to f=16
        b_q = _quantize(conv.bias.detach().cpu())  # f=16
        out = out + b_q.view(1, -1, 1, 1)
        return out.to(torch.int64)

    def _pool_fixed(self, x_int: torch.Tensor, inv_fp: int, k: int) -> torch.Tensor:
        summed = torch.trunc(F.avg_pool2d(x_int.double(), kernel_size=k, stride=k) * (k * k))
        return summed.to(torch.int64) * inv_fp

    def _fc_matmul(self, x_int: torch.Tensor, linear: nn.Linear) -> torch.Tensor:
        w = _quantize(linear.weight.detach().cpu().T).to(torch.int64)  # f=16
        b = _quantize(linear.bias.detach().cpu()).to(torch.int64)  # f=16 (legacy quirk)
        return x_int.to(torch.int64).cpu() @ w + b

    def _run_fixed_point(
        self,
        images: torch.Tensor,
        plan: TruncationPlan,
        *,
        return_bounds: bool = False,
        return_layers: bool = False,
    ):
        orig_device = images.device
        _, fixed = preprocess_batch_rgb(images.cpu())
        bounds: dict[str, float] = {}
        k = plan.pool_k
        inv_fp = plan.pool_inv_fp

        # conv1 + ReLU (π1)
        c1 = self._conv_fixed_int(fixed, self.conv1)
        after_conv1 = apply_client_action(c1, "relu")
        if return_bounds:
            bounds["after_conv1"] = float(after_conv1.abs().max().item())

        # pool1 (f=28) → shift 28→16 (π2)
        p1 = self._pool_fixed(after_conv1, inv_fp, k)
        if return_bounds:
            bounds["after_pool1_pre_shift"] = float(p1.abs().max().item())
        s1 = apply_client_action(p1, "shift", shift_bits_val=plan.shift_pool)

        # conv2 + ReLU (π3)
        c2 = self._conv_fixed_int(s1, self.conv2)
        after_conv2 = apply_client_action(c2, "relu")
        if return_bounds:
            bounds["after_conv2_pre_relu"] = float(after_conv2.abs().max().item())

        # pool2 (f=28) → shift 28→16 (π4)
        p2 = self._pool_fixed(after_conv2, inv_fp, k)
        if return_bounds:
            bounds["after_pool2_pre_shift"] = float(p2.abs().max().item())
        s2 = apply_client_action(p2, "shift", shift_bits_val=plan.shift_pool)
        flat = s2.reshape(s2.shape[0], -1)

        # fc1 (f=32) → relu_then_shift 32→16 (π5)
        h1 = self._fc_matmul(flat, self.fc1)
        if return_bounds:
            bounds["after_fc1_pre_relu"] = float(h1.abs().max().item())
        after_fc1 = apply_client_action(h1, "relu_then_shift", shift_bits_val=plan.shift_fc)

        # fc2 (f=32) → relu_then_shift 32→16 (π6)
        h2 = self._fc_matmul(after_fc1, self.fc2)
        if return_bounds:
            bounds["after_fc2_pre_relu"] = float(h2.abs().max().item())
        after_fc2 = apply_client_action(h2, "relu_then_shift", shift_bits_val=plan.shift_fc)

        # fc3 (f=32) → argmax (no client回传)
        h3 = self._fc_matmul(after_fc2, self.fc3)
        logits = h3.double() / (2.0**plan.shift_fc)

        if return_layers:
            layers = {
                "after_conv1": after_conv1,
                "after_pool1": s1.reshape(s1.shape[0], -1),
                "after_conv2": after_conv2,
                "after_pool2": flat,
                "after_fc1": after_fc1,
                "after_fc2": after_fc2,
                "after_fc3": h3,
            }
            return layers, (bounds if return_bounds else None), orig_device

        if return_bounds:
            return logits.to(orig_device), bounds
        return logits.to(orig_device)

    def forward_fixed_point(
        self,
        images: torch.Tensor,
        *,
        plan: TruncationPlan | None = None,
        return_bounds: bool = False,
    ):
        plan = plan or self.plan
        if return_bounds:
            return self._run_fixed_point(images, plan, return_bounds=True)
        return self._run_fixed_point(images, plan)

    def forward_fixed_point_layers(
        self, images: torch.Tensor, *, plan: TruncationPlan | None = None
    ) -> dict[str, torch.Tensor]:
        plan = plan or self.plan
        layers, _, orig_device = self._run_fixed_point(
            images, plan, return_bounds=False, return_layers=True
        )
        return {k: v.to(orig_device) for k, v in layers.items()}

    # ---- QAT path (STE through truncation boundaries) ------------------------
    def _conv_fixed_ste(self, x: torch.Tensor, conv: nn.Conv2d) -> torch.Tensor:
        scale = float(_SCALE)
        w_q = _ste_truncate_toward_zero(conv.weight * scale)
        # exact integer value (float64) + STE gradient via float path
        with torch.no_grad():
            acc_exact = torch.trunc(
                F.conv2d(x.detach().double().cpu(), w_q.detach().double().cpu())
            )
            out_exact = torch.div(acc_exact, scale, rounding_mode="floor")
        acc_ste = F.conv2d(x, w_q)
        out_ste = torch.trunc(acc_ste / scale)
        out = out_exact.float().to(x.device) + (out_ste - out_ste.detach())
        b_q = _ste_truncate_toward_zero(conv.bias * scale)
        return out + b_q.view(1, -1, 1, 1)

    def _fc_ste(self, x: torch.Tensor, linear: nn.Linear) -> torch.Tensor:
        scale = float(_SCALE)
        w_q = _ste_truncate_toward_zero(linear.weight.T * scale)
        b_q = _ste_truncate_toward_zero(linear.bias * scale)
        with torch.no_grad():
            out_exact = (
                x.detach().to(torch.int64).cpu().double()
                @ w_q.detach().double().cpu()
                + b_q.detach().double().cpu()
            )
        out_ste = x.float() @ w_q + b_q
        return out_exact.float().to(x.device) + (out_ste - out_ste.detach())

    def forward_fixed_point_train(
        self, images: torch.Tensor, plan: TruncationPlan | None = None
    ) -> torch.Tensor:
        plan = plan or self.plan
        device = images.device
        _, fixed = preprocess_batch_rgb(images.cpu())
        x = fixed.double().to(device).float()

        x = self._conv_fixed_ste(x, self.conv1)
        x = F.relu(x)
        x = torch.trunc(F.avg_pool2d(x, plan.pool_k) * (plan.pool_k**2)) * float(plan.pool_inv_fp)
        x = _ste_shift_bits(x, plan.shift_pool)

        x = self._conv_fixed_ste(x, self.conv2)
        x = F.relu(x)
        x = torch.trunc(F.avg_pool2d(x, plan.pool_k) * (plan.pool_k**2)) * float(plan.pool_inv_fp)
        x = _ste_shift_bits(x, plan.shift_pool)
        x = x.reshape(x.shape[0], -1)

        x = self._fc_ste(x, self.fc1)
        x = F.relu(x)
        x = _ste_shift_bits(x, plan.shift_fc)
        x = self._fc_ste(x, self.fc2)
        x = F.relu(x)
        x = _ste_shift_bits(x, plan.shift_fc)
        x = self._fc_ste(x, self.fc3)
        return x / (2.0**plan.shift_fc)

    def forward(self, images: torch.Tensor, *, mode: str = "float") -> torch.Tensor:
        if mode == "float":
            return self.forward_float(images)
        if mode == "fixed_train":
            return self.forward_fixed_point_train(images)
        if mode == "fixed":
            return self.forward_fixed_point(images)
        raise ValueError(f"unknown mode: {mode}")
