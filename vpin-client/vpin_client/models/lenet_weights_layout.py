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
    weight_conv1: str = "conv1_weight_6_3_5_5.npy"
    bias_conv1: str = "conv1_bias_6.npy"
    weight_conv2: str = "conv2_weight_16_6_5_5.npy"
    bias_conv2: str = "conv2_bias_16.npy"
    weight_c3: str = "c3_weight_400_120.npy"
    bias_c3: str = "c3_bias_120.npy"
    weight_fc4: str = "fc4_weight_120_84.npy"
    bias_fc4: str = "fc4_bias_84.npy"
    weight_fc5: str = "fc5_weight_84_10.npy"
    bias_fc5: str = "fc5_bias_10.npy"

    @property
    def required_files(self) -> tuple[str, ...]:
        return (
            self.weight_conv1,
            self.bias_conv1,
            self.weight_conv2,
            self.bias_conv2,
            self.weight_c3,
            self.bias_c3,
            self.weight_fc4,
            self.bias_fc4,
            self.weight_fc5,
            self.bias_fc5,
        )


_LENET_CIFAR_BUNDLE = LeNetCifarBundleLayout()

LENET_LAYER_LAYOUTS = {
    "conv1": LeNetLayerLayout(LeNetLayerType.CONV1, (6, 3, 5, 5), "weight_conv1_*.npy"),
    "conv2": LeNetLayerLayout(LeNetLayerType.CONV2, (16, 6, 5, 5), "weight_conv2_*.npy"),
    "fc1": LeNetLayerLayout(LeNetLayerType.FC1, (400, 120), "weight_fc1_*.npy"),
    "fc2": LeNetLayerLayout(LeNetLayerType.FC2, (120, 84), "weight_fc2_*.npy"),
    "fc3": LeNetLayerLayout(LeNetLayerType.FC3, (10, 84), "weight_fc3_*.npy"),
}


@dataclass(frozen=True)
class LeNetMnistBundleLayout:
    """LeNet-MNIST homomorphic weight bundle (1-channel input)."""

    network_id: str = "lenet_mnist"
    weight_conv1: str = "conv1_weight_6_1_5_5.npy"
    bias_conv1: str = "conv1_bias_6.npy"
    weight_conv2: str = "conv2_weight_16_6_5_5.npy"
    bias_conv2: str = "conv2_bias_16.npy"
    weight_c3: str = "c3_weight_400_120.npy"
    bias_c3: str = "c3_bias_120.npy"
    weight_fc4: str = "fc4_weight_120_84.npy"
    bias_fc4: str = "fc4_bias_84.npy"
    weight_fc5: str = "fc5_weight_84_10.npy"
    bias_fc5: str = "fc5_bias_10.npy"

    @property
    def required_files(self) -> tuple[str, ...]:
        return (
            self.weight_conv1,
            self.bias_conv1,
            self.weight_conv2,
            self.bias_conv2,
            self.weight_c3,
            self.bias_c3,
            self.weight_fc4,
            self.bias_fc4,
            self.weight_fc5,
            self.bias_fc5,
        )


_LENET_MNIST_BUNDLE = LeNetMnistBundleLayout()


def get_lenet_layout(layer_name: str | None = None, variant: str = "cifar") -> LeNetCifarBundleLayout | LeNetMnistBundleLayout | LeNetLayerLayout | None:
    """Return full bundle layout (no arg) or a single layer spec."""
    if layer_name is None:
        if variant == "mnist":
            return _LENET_MNIST_BUNDLE
        return _LENET_CIFAR_BUNDLE
    return LENET_LAYER_LAYOUTS.get(layer_name)


def is_lenet_model(model_id: str) -> bool:
    key = model_id.lower()
    return "lenet" in key or model_id in ("mnist-lenet", "lenet-mnist", "lenet-cifar10")
