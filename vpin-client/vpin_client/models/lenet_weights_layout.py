"""LeNet-CIFAR npy bundle layout (10-file conv+FC) and per-layer specs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LeNetLayerType(str, Enum):
    CONV1 = "conv1"
    CONV2 = "conv2"
    FC1 = "fc1"
    FC2 = "fc2"
    FC3 = "fc3"


@dataclass(frozen=True)
class LeNetLayerLayout:
    layer_type: LeNetLayerType
    shape: tuple[int, ...]
    expected_file_pattern: str


@dataclass(frozen=True)
class LeNetCifarBundleLayout:
    """Full LeNet-CIFAR homomorphic weight bundle (matches model_training exports)."""

    network_id: str = "lenet_cifar"
    weight_conv1: str = "weight_conv1_6_3_5_5.npy"
    bias_conv1: str = "bias_conv1_6.npy"
    weight_conv2: str = "weight_conv2_16_6_5_5.npy"
    bias_conv2: str = "bias_conv2_16.npy"
    weight_fc1: str = "weight_fc1_400_120.npy"
    bias_fc1: str = "bias_fc1_120.npy"
    weight_fc2: str = "weight_fc2_120_84.npy"
    bias_fc2: str = "bias_fc2_84.npy"
    weight_fc3: str = "weight_fc3_84_10.npy"
    bias_fc3: str = "bias_fc3_10.npy"

    @property
    def required_files(self) -> tuple[str, ...]:
        return (
            self.weight_conv1,
            self.bias_conv1,
            self.weight_conv2,
            self.bias_conv2,
            self.weight_fc1,
            self.bias_fc1,
            self.weight_fc2,
            self.bias_fc2,
            self.weight_fc3,
            self.bias_fc3,
        )


_LENET_CIFAR_BUNDLE = LeNetCifarBundleLayout()

LENET_LAYER_LAYOUTS = {
    "conv1": LeNetLayerLayout(LeNetLayerType.CONV1, (6, 3, 5, 5), "weight_conv1_*.npy"),
    "conv2": LeNetLayerLayout(LeNetLayerType.CONV2, (16, 6, 5, 5), "weight_conv2_*.npy"),
    "fc1": LeNetLayerLayout(LeNetLayerType.FC1, (400, 120), "weight_fc1_*.npy"),
    "fc2": LeNetLayerLayout(LeNetLayerType.FC2, (120, 84), "weight_fc2_*.npy"),
    "fc3": LeNetLayerLayout(LeNetLayerType.FC3, (10, 84), "weight_fc3_*.npy"),
}


def get_lenet_layout(layer_name: str | None = None) -> LeNetCifarBundleLayout | LeNetLayerLayout | None:
    """Return full CIFAR bundle layout (no arg) or a single layer spec."""
    if layer_name is None:
        return _LENET_CIFAR_BUNDLE
    return LENET_LAYER_LAYOUTS.get(layer_name)


def is_lenet_model(model_id: str) -> bool:
    key = model_id.lower()
    return "lenet" in key or model_id in ("mnist-lenet", "lenet-mnist", "lenet-cifar10")
