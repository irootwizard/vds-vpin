"""ResNet18 + Block Linearization support for new_resnet_block.

Standard usage (calibration workflow):
    model = ResNet18()
    ckpt = torch.load("new_resnet/outputs/.../checkpoint.pt")
    model.load_state_dict(ckpt["state_dict"])

    # After running calibrate.py:
    linearize_blocks(model,
                     targets={"layer1_both", "layer2_b2", "layer3_b2", "layer4_b2"},
                     weights_dir=Path("block_linear_weights"))
    # model is now partially linearized; evaluate accuracy or export weights for AHE.

AHE note:
    A LinearizedBlock replaces one or more identity-shortcut BasicBlocks with a
    single matrix multiply (A @ x).  In the AHE protocol this saves client rounds:
      Original:   conv1 → [client: relu+shift] → conv2+sc → [client: relu+shift]  (2 rounds)
      Linearized: A @ enc_x → enc_y (f=32)     → [client: shift only]             (1 round)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Standard ResNet building blocks (identical to new_resnet)
# ---------------------------------------------------------------------------

class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_planes: int, planes: int, stride: int = 1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_planes, planes, 3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, planes, 1, stride=stride, bias=False),
                nn.BatchNorm2d(planes),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        return F.relu(out)


# ---------------------------------------------------------------------------
# LinearizedBlock: calibrated linear approximation of one or more BasicBlocks
# ---------------------------------------------------------------------------

class LinearizedBlock(nn.Module):
    """Replaces one or more identity-shortcut BasicBlocks with a linear mapping.

    mode='channel':
        A ∈ R^{C_out × C_in}, applied per spatial position (equivalent to 1×1 conv).
        Feasible for any spatial size; captures channel mixing only.
        Matrix size: C² floats (e.g. 64²=4096 for layer1).

    mode='full':
        A ∈ R^{D × D} where D = C × H × W, full spatial linear mapping.
        Feasible only for small D. For layer4 B2: D = 512×4×4 = 8192 → ~256 MB.

    Weights are initialised to the identity (block ≈ identity for small residuals).
    Call load_weight_numpy() after calibrate.py to replace with the fitted A.
    """

    def __init__(self, channels: int, h: int, w: int, mode: str = 'channel'):
        super().__init__()
        self.channels = channels
        self.h = h
        self.w = w
        self.mode = mode
        if mode == 'channel':
            self.weight = nn.Parameter(torch.eye(channels))
        elif mode == 'full':
            D = channels * h * w
            self.weight = nn.Parameter(torch.eye(D))
        else:
            raise ValueError(f"mode must be 'channel' or 'full', got '{mode}'")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.mode == 'channel':
            # (B, C, H, W) → per-pixel channel linear → (B, C, H, W)
            return F.linear(x.permute(0, 2, 3, 1), self.weight).permute(0, 3, 1, 2)
        else:
            B, C, H, W = x.shape
            D = C * H * W
            return F.linear(x.reshape(B, D), self.weight).reshape(B, C, H, W)

    def load_weight_numpy(self, arr: np.ndarray) -> None:
        """Load calibrated A matrix from calibrate.py output."""
        t = torch.from_numpy(arr).float()
        if t.shape != self.weight.shape:
            raise ValueError(f"Expected shape {self.weight.shape}, got {t.shape}")
        with torch.no_grad():
            self.weight.copy_(t)


# ---------------------------------------------------------------------------
# Standard ResNet (identical to new_resnet — used for calibration)
# ---------------------------------------------------------------------------

class ResNet(nn.Module):
    def __init__(self, block: type, num_blocks: list[int], num_classes: int = 10):
        super().__init__()
        self.in_planes = 64
        self.conv1  = nn.Conv2d(3, 64, 3, stride=1, padding=1, bias=False)
        self.bn1    = nn.BatchNorm2d(64)
        self.layer1 = self._make_layer(block, 64,  num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, 128, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, 256, num_blocks[2], stride=2)
        self.layer4 = self._make_layer(block, 512, num_blocks[3], stride=2)
        self.linear = nn.Linear(512 * block.expansion, num_classes)

    def _make_layer(self, block: type, planes: int, num_blocks: int, stride: int) -> nn.Sequential:
        strides = [stride] + [1] * (num_blocks - 1)
        layers = []
        for s in strides:
            layers.append(block(self.in_planes, planes, s))
            self.in_planes = planes * block.expansion
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = F.avg_pool2d(out, 4)
        out = out.view(out.size(0), -1)
        return self.linear(out)


def ResNet18() -> ResNet:
    """Standard ResNet18 — identical to new_resnet, used for calibration and baseline."""
    return ResNet(BasicBlock, [2, 2, 2, 2])


# ---------------------------------------------------------------------------
# Block linearization registry and in-place replacement utility
# ---------------------------------------------------------------------------

# Each entry: layer_attr, block_index (None = whole layer), C, H, W, mode
# block_index=None: replace the entire nn.Sequential with one LinearizedBlock
#                   (used for layer1 where both blocks are merged)
# block_index=k:    replace layer[k] only
_LINEARIZE_TARGETS: dict[str, tuple] = {
    'layer1_both': ('layer1', None, 64,  32, 32, 'channel'),
    'layer2_b2':   ('layer2', 1,   128,  16, 16, 'channel'),
    'layer3_b2':   ('layer3', 1,   256,   8,  8, 'channel'),
    'layer4_b2':   ('layer4', 1,   512,   4,  4, 'full'),
}


def linearize_blocks(
    model: ResNet,
    targets: set[str],
    weights_dir: Path,
) -> ResNet:
    """Replace identity blocks in model with pre-calibrated LinearizedBlocks.

    The model's other weights are unchanged (downsample-shortcut blocks remain as
    standard BasicBlocks).  This modifies model in-place and also returns it.

    Args:
        model:       ResNet18 with original new_resnet weights loaded.
        targets:     Any subset of {'layer1_both', 'layer2_b2', 'layer3_b2', 'layer4_b2'}.
        weights_dir: Directory containing A_{target}.npy files from calibrate.py.

    Raises:
        FileNotFoundError: If a required A_{target}.npy is missing.
    """
    for name in sorted(targets):
        if name not in _LINEARIZE_TARGETS:
            raise ValueError(f"Unknown target '{name}'.  Valid: {set(_LINEARIZE_TARGETS)}")
        layer_attr, block_idx, C, H, W, mode = _LINEARIZE_TARGETS[name]

        weight_path = weights_dir / f"A_{name}.npy"
        if not weight_path.exists():
            raise FileNotFoundError(
                f"Calibrated weight not found: {weight_path}\n"
                f"Run:  python -m model_training.new_resnet_block.calibrate "
                f"--checkpoint <ckpt> --targets {name}"
            )

        lb = LinearizedBlock(C, H, W, mode=mode)
        lb.load_weight_numpy(np.load(weight_path))

        layer = getattr(model, layer_attr)
        if block_idx is None:
            setattr(model, layer_attr, lb)
        else:
            layer[block_idx] = lb
        print(f"[linearize_blocks] Replaced {layer_attr}[{block_idx}] → LinearizedBlock({mode})")

    return model
