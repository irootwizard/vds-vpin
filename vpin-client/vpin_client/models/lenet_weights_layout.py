"""LeNet weight layout definitions for vPIN."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class LeNetLayerType(str, Enum):
    """LeNet layer types."""
    CONV1 = "conv1"
    CONV2 = "conv2"
    FC1 = "fc1"
    FC2 = "fc2"


@dataclass
class LeNetWeightLayout:
    """Weight layout specification for LeNet layers."""
    layer_type: LeNetLayerType
    shape: tuple[int, ...]
    expected_file_pattern: str


# Standard LeNet-5 architecture for MNIST
# Input: 1x32x32 → Conv1(6@5x5) → Pool(2x2) → Conv2(16@5x5) → Pool(2x2) → FC1(120) → FC2(84) → FC3(10)
LENET_MNIST_LAYOUTS = {
    "conv1": LeNetWeightLayout(
        layer_type=LeNetLayerType.CONV1,
        shape=(6, 1, 5, 5),
        expected_file_pattern="weight_conv1_*.npy"
    ),
    "conv2": LeNetWeightLayout(
        layer_type=LeNetLayerType.CONV2,
        shape=(16, 6, 5, 5),
        expected_file_pattern="weight_conv2_*.npy"
    ),
    "fc1": LeNetWeightLayout(
        layer_type=LeNetLayerType.FC1,
        shape=(120, 400),
        expected_file_pattern="weight_fc1_*.npy"
    ),
    "fc2": LeNetWeightLayout(
        layer_type=LeNetLayerType.FC2,
        shape=(84, 120),
        expected_file_pattern="weight_fc2_*.npy"
    ),
}


def get_lenet_layout(layer_name: str) -> LeNetWeightLayout | None:
    """Get layout specification for a LeNet layer.

    Args:
        layer_name: Name of the layer (conv1, conv2, fc1, fc2)

    Returns:
        LeNetWeightLayout if found, None otherwise
    """
    return LENET_MNIST_LAYOUTS.get(layer_name)


def is_lenet_model(model_id: str) -> bool:
    """Check if model ID corresponds to a LeNet architecture.

    Args:
        model_id: Model identifier

    Returns:
        True if model is LeNet-based
    """
    return "lenet" in model_id.lower() or model_id in ["mnist-lenet", "lenet-mnist"]
