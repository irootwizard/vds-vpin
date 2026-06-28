"""PyTorch Network B — same conv/pool as A, FC 64→32→10."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from model_training.network_b.fixed_point import apply_client_action
from model_training.network_b.preprocess import preprocess_batch_uint8, uint8_to_float_input
from model_training.network_b.truncation_config import DEFAULT_PLAN, FIXED_POINT_BITS, TruncationPlan

CONV_KERNEL = torch.tensor(
    [[[1.0, 0.0, 1.0], [2.0, 0.0, 2.0], [1.0, 0.0, 1.0]]],
    dtype=torch.float32,
).unsqueeze(0)


def _sum_pool4x4(x: torch.Tensor) -> torch.Tensor:
    """x: (B, C, 32, 32) -> (B, C, 8, 8) via sum over 4x4 windows."""
    if not x.is_floating_point():
        x = x.float()
    return F.avg_pool2d(x, kernel_size=4, stride=4) * 16.0


def _pool_fixed(x: torch.Tensor, inv_fp: int) -> torch.Tensor:
    """Sum pool 4x4 then multiply by 10-bit fixed 1/16 — integer semantics."""
    summed = _sum_pool4x4(x).round()
    return (summed.to(torch.int64) * inv_fp).to(torch.int32)


def _quantize_fc_weight(w: torch.Tensor) -> torch.Tensor:
    """Truncate to int32 fixed-point — matches real_to_fixed_point (astype, not round)."""
    return (w * (2**FIXED_POINT_BITS)).to(torch.int32)


def _fc_matmul(x: torch.Tensor, weight: torch.Tensor, bias: torch.Tensor) -> torch.Tensor:
    """Integer FC at f=32 — int64 matmul, no pre-TReLU int32 cast (legacy Client.py / Server FCLayer)."""
    w = _quantize_fc_weight(weight.T).to(torch.int64)
    b = _quantize_fc_weight(bias).to(torch.int64)
    return x.to(torch.int64) @ w + b


_fc_int32 = _fc_matmul  # backward-compatible alias


def _fc_ste(x: torch.Tensor, weight: torch.Tensor, bias: torch.Tensor) -> torch.Tensor:
    """Differentiable FC — forward matches _fc_matmul, STE backward through weights."""
    scale = float(2**FIXED_POINT_BITS)
    w = weight.T * scale
    b = bias * scale
    w_q = _ste_truncate_toward_zero(w)
    b_q = _ste_truncate_toward_zero(b)

    out_int = x.to(torch.int64).cpu() @ w_q.detach().cpu().to(torch.int64) + b_q.detach().cpu().to(
        torch.int64
    )
    out = out_int.float().to(x.device)
    out_ste = x.float() @ w_q + b_q
    return out + (out_ste - out_ste.detach())


def _ste_truncate_toward_zero(x: torch.Tensor) -> torch.Tensor:
    """STE for numpy/torch int32 truncate toward zero."""
    truncated = torch.trunc(x)
    return x + (truncated - x).detach()


def _ste_shift_bits(x: torch.Tensor, from_bits: int, to_bits: int = FIXED_POINT_BITS) -> torch.Tensor:
    reals = x.float() / (2.0**from_bits)
    scaled = reals * (2.0**to_bits)
    return _ste_truncate_toward_zero(scaled)


def _pool_fixed_ste(x: torch.Tensor, inv_fp: int) -> torch.Tensor:
    summed = _sum_pool4x4(x).round()
    return _ste_truncate_toward_zero(summed * float(inv_fp))


class NetworkB(nn.Module):
    def __init__(self, plan: TruncationPlan | None = None) -> None:
        super().__init__()
        self.plan = plan or DEFAULT_PLAN
        self.register_buffer("conv_weight", CONV_KERNEL.clone())
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 10)
        self._init_fc()

    def _init_fc(self) -> None:
        nn.init.xavier_uniform_(self.fc1.weight)
        nn.init.zeros_(self.fc1.bias)
        nn.init.xavier_uniform_(self.fc2.weight)
        nn.init.zeros_(self.fc2.bias)

    def trainable_parameters(self):
        return list(self.fc1.parameters()) + list(self.fc2.parameters())

    def _conv(self, x: torch.Tensor) -> torch.Tensor:
        return F.conv2d(x, self.conv_weight, padding=1)

    def forward_float(self, images: torch.Tensor) -> torch.Tensor:
        """images: (B,1,28,28) uint8 from MNIST."""
        x = uint8_to_float_input(images)
        x = self._conv(x)
        x = F.relu(x)
        x = _sum_pool4x4(x) / 16.0
        x = x.reshape(x.shape[0], -1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x

    def _conv_fixed_int(self, fixed: torch.Tensor) -> torch.Tensor:
        """Integer conv on CPU — avoids CUDA float conv rounding vs homomorphic path."""
        return F.conv2d(fixed.float().cpu(), self.conv_weight.cpu(), padding=1).round()

    def _run_fixed_point(
        self,
        images: torch.Tensor,
        plan: TruncationPlan,
        *,
        return_bounds: bool = False,
        return_layers: bool = False,
    ):
        orig_device = images.device
        _, fixed = preprocess_batch_uint8(images.cpu())

        x = self._conv_fixed_int(fixed)
        bounds: dict[str, float] = {}
        if return_bounds:
            bounds["after_conv"] = float(x.abs().max().item())

        after_conv = apply_client_action(x, "relu")
        x = _pool_fixed(after_conv, plan.pool_inv_fp)
        if return_bounds:
            bounds["after_pool_pre_shift"] = float(x.abs().max().item())

        x = apply_client_action(x, "shift", shift_bits_val=plan.shift_pool)
        after_pool = x.reshape(x.shape[0], -1)

        x_fc1 = _fc_matmul(after_pool, self.fc1.weight.data.cpu(), self.fc1.bias.data.cpu())
        if return_bounds:
            bounds["after_fc1_pre_relu"] = float(x_fc1.abs().max().item())

        after_fc1 = apply_client_action(x_fc1, "relu_then_shift", shift_bits_val=plan.shift_fc1)
        x_fc2 = _fc_matmul(after_fc1, self.fc2.weight.data.cpu(), self.fc2.bias.data.cpu())
        if return_bounds:
            bounds["after_fc2_pre_relu"] = float(x_fc2.abs().max().item())

        after_fc2 = apply_client_action(x_fc2, "relu_only")
        logits = after_fc2.float() / (2**FIXED_POINT_BITS)

        if return_layers:
            layers = {
                "after_conv": after_conv,
                "after_pool": after_pool,
                "after_fc1": after_fc1,
                "after_fc2": after_fc2,
            }
            return layers, bounds if return_bounds else None, orig_device

        if return_bounds:
            return logits.to(orig_device), bounds
        return logits.to(orig_device)

    def forward_fixed_point(
        self,
        images: torch.Tensor,
        *,
        plan: TruncationPlan | None = None,
        return_bounds: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, dict[str, float]]:
        plan = plan or self.plan
        if return_bounds:
            logits, bounds = self._run_fixed_point(images, plan, return_bounds=True)
            return logits, bounds
        return self._run_fixed_point(images, plan)

    def forward_fixed_point_layers(
        self,
        images: torch.Tensor,
        *,
        plan: TruncationPlan | None = None,
    ) -> dict[str, torch.Tensor]:
        plan = plan or self.plan
        layers, _, orig_device = self._run_fixed_point(
            images, plan, return_bounds=False, return_layers=True
        )
        return {k: v.to(orig_device) for k, v in layers.items()}

    def forward_fixed_point_train(self, images: torch.Tensor, plan: TruncationPlan | None = None) -> torch.Tensor:
        """QAT aligned with _run_fixed_point (STE at truncate boundaries)."""
        plan = plan or self.plan
        device = images.device
        _, fixed = preprocess_batch_uint8(images.cpu())

        with torch.no_grad():
            x = self._conv_fixed_int(fixed).to(device).float()
        x = F.relu(x)

        x = _pool_fixed_ste(x, plan.pool_inv_fp)
        x = _ste_shift_bits(x, plan.shift_pool)
        x = x.reshape(x.shape[0], -1)

        x = _fc_ste(x, self.fc1.weight, self.fc1.bias)
        x = F.relu(x)
        x = _ste_shift_bits(x, plan.shift_fc1)

        x = _fc_ste(x, self.fc2.weight, self.fc2.bias)
        x = F.relu(x)
        return x / (2**FIXED_POINT_BITS)

    def forward(self, images: torch.Tensor, *, mode: str = "float") -> torch.Tensor:
        if mode == "float":
            return self.forward_float(images)
        if mode == "fixed_train":
            return self.forward_fixed_point_train(images)
        if mode == "fixed":
            return self.forward_fixed_point(images)  # type: ignore[return-value]
        raise ValueError(f"unknown mode: {mode}")
