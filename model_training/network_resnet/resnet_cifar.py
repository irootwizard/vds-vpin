"""CIFAR-10 ResNet (ResNet-20 style) for AHE dynamic-parse diagnostics only.

Reference topology: akamaster/pytorch_resnet_cifar10 (paper-faithful shallow ResNet).
Not trained for AHE deploy — used to exercise AHEModelAnalyzer on deeper CNNs.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


def conv3x3(in_planes: int, out_planes: int, stride: int = 1) -> nn.Conv2d:
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_planes: int, planes: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = conv3x3(in_planes, planes, stride)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, planes, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = F.relu(out)
        return out


class ResNetCIFAR(nn.Module):
    """ResNet-20/32/44/56/110 depth = 6*n+2 blocks on CIFAR-10."""

    MODEL_ID = "resnet-cifar10-diagnostic"
    NETWORK_FAMILY = "resnet_cifar"
    DATASET = "cifar10"

    def __init__(self, block: type[BasicBlock] = BasicBlock, num_blocks: list[int] | None = None) -> None:
        super().__init__()
        num_blocks = num_blocks or [3, 3, 3]
        self.in_planes = 16
        self.conv1 = nn.Conv2d(3, 16, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(16)
        self.layer1 = self._make_layer(block, 16, num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, 32, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, 64, num_blocks[2], stride=2)
        self.avgpool = nn.AvgPool2d(8)
        self.fc = nn.Linear(64 * block.expansion, 10)

    def _make_layer(self, block: type[BasicBlock], planes: int, num_blocks: int, stride: int) -> nn.Sequential:
        strides = [stride] + [1] * (num_blocks - 1)
        layers: list[nn.Module] = []
        for s in strides:
            layers.append(block(self.in_planes, planes, s))
            self.in_planes = planes * block.expansion
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.avgpool(out)
        out = out.view(out.size(0), -1)
        return self.fc(out)


def resnet20() -> ResNetCIFAR:
    return ResNetCIFAR(BasicBlock, [3, 3, 3])


def resnet32() -> ResNetCIFAR:
    return ResNetCIFAR(BasicBlock, [5, 5, 5])


def resnet56() -> ResNetCIFAR:
    return ResNetCIFAR(BasicBlock, [9, 9, 9])


class ResNet18CIFAR(nn.Module):
    """ResNet-18 on CIFAR-10 (4 stages, [2,2,2,2] BasicBlocks).

    Reference: patr1ckzhu/resnet-cifar10 — 3×3 stem, no ImageNet 7×7/maxpool.
    """

    MODEL_ID = "resnet18-cifar10"
    NETWORK_FAMILY = "resnet_cifar"
    DATASET = "cifar10"

    def __init__(self, block: type[BasicBlock] = BasicBlock, num_blocks: list[int] | None = None) -> None:
        super().__init__()
        num_blocks = num_blocks or [2, 2, 2, 2]
        self.in_planes = 64
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.layer1 = self._make_layer(block, 64, num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, 128, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, 256, num_blocks[2], stride=2)
        self.layer4 = self._make_layer(block, 512, num_blocks[3], stride=2)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(512 * block.expansion, 10)

    def _make_layer(self, block: type[BasicBlock], planes: int, num_blocks: int, stride: int) -> nn.Sequential:
        strides = [stride] + [1] * (num_blocks - 1)
        layers: list[nn.Module] = []
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
        out = self.avgpool(out)
        out = out.view(out.size(0), -1)
        return self.fc(out)


def resnet18() -> ResNet18CIFAR:
    return ResNet18CIFAR(BasicBlock, [2, 2, 2, 2])
