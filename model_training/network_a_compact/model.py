"""Network A compact — 3 client rounds (ReLU only), no client shift rounds."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from model_training.network_a.model import CONV_KERNEL, NetworkA, _fc_matmul, _sum_pool4x4
from model_training.network_a.preprocess import preprocess_batch_uint8
from model_training.network_a_compact.fixed_point import (
    apply_client_action,
    apply_fc1_boundary,
    check_reencrypt_range,
)
from model_training.network_a_compact.truncation_config import POOL_COMPACT_DIV, CompactPlan, QuantMode

FIXED_POINT_BITS = 16


def _pool_compact(x: torch.Tensor) -> torch.Tensor:
    """Sum pool 4×4 then //16 — bit-exact with baseline pool + client shift."""
    summed = _sum_pool4x4(x.float()).round()
    return (summed.to(torch.int64) // POOL_COMPACT_DIV).to(torch.int32)


class NetworkACompact(nn.Module):
    """Same topology as Network A; pool shift absorbed server-side (sum//16)."""

    def __init__(self, plan: CompactPlan | None = None) -> None:
        super().__init__()
        self.plan = plan or CompactPlan()
        self.register_buffer("conv_weight", CONV_KERNEL.clone())
        self.fc1 = nn.Linear(64, 16)
        self.fc2 = nn.Linear(16, 10)
        self._init_fc()

    def _init_fc(self) -> None:
        nn.init.xavier_uniform_(self.fc1.weight)
        nn.init.zeros_(self.fc1.bias)
        nn.init.xavier_uniform_(self.fc2.weight)
        nn.init.zeros_(self.fc2.bias)

    @classmethod
    def from_network_a(cls, base: NetworkA, *, quant_mode: QuantMode = "int32") -> NetworkACompact:
        plan = CompactPlan(quant_mode=quant_mode)
        m = cls(plan=plan)
        m.fc1.load_state_dict(base.fc1.state_dict())
        m.fc2.load_state_dict(base.fc2.state_dict())
        return m

    def _conv_fixed_int(self, fixed: torch.Tensor) -> torch.Tensor:
        return F.conv2d(fixed.float().cpu(), self.conv_weight.cpu(), padding=1).round()

    def forward_fixed_point(
        self,
        images: torch.Tensor,
        *,
        return_bounds: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, dict[str, float]]:
        orig_device = images.device
        _, fixed = preprocess_batch_uint8(images.cpu())
        qmode = self.plan.quant_mode

        x = self._conv_fixed_int(fixed)
        bounds: dict[str, float] = {}
        if return_bounds:
            bounds["after_conv"] = float(x.abs().max().item())

        after_conv = apply_client_action(x.numpy(), "relu", quant_mode=qmode)
        check_reencrypt_range(after_conv, qmode, "after_conv")
        x = torch.from_numpy(after_conv).to(torch.int64)

        x = _pool_compact(x)
        if return_bounds:
            bounds["after_pool_f16"] = float(x.abs().max().item())

        flat = x.reshape(x.shape[0], -1).to(torch.int64)
        x_fc1 = _fc_matmul(flat, self.fc1.weight.data.cpu(), self.fc1.bias.data.cpu())
        if return_bounds:
            bounds["after_fc1_pre_relu"] = float(x_fc1.abs().max().item())

        after_fc1 = apply_fc1_boundary(x_fc1.numpy(), quant_mode=qmode)
        check_reencrypt_range(after_fc1, qmode, "after_fc1")
        x_fc2_in = torch.from_numpy(after_fc1).to(torch.int64)

        x_fc2 = _fc_matmul(x_fc2_in, self.fc2.weight.data.cpu(), self.fc2.bias.data.cpu())
        if return_bounds:
            bounds["after_fc2_pre_relu"] = float(x_fc2.abs().max().item())

        after_fc2 = apply_client_action(x_fc2.numpy(), "relu_only", quant_mode=qmode)
        logits = torch.from_numpy(after_fc2).float() / (2**FIXED_POINT_BITS)

        if return_bounds:
            return logits.to(orig_device), bounds
        return logits.to(orig_device)

    def forward_float(self, images: torch.Tensor) -> torch.Tensor:
        base = NetworkA(plan=None)
        base.fc1.load_state_dict(self.fc1.state_dict())
        base.fc2.load_state_dict(self.fc2.state_dict())
        return base.forward_float(images)
