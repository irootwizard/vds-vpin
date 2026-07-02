"""Network topology constants (Network A) — semantic port of cnn_networks layout."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvSpec:
    kernel_h: int
    kernel_w: int
    in_channels: int
    out_channels: int
    stride: int = 1
    padding: int = 0


@dataclass(frozen=True)
class PoolSpec:
    kernel_h: int
    kernel_w: int
    stride: int


@dataclass(frozen=True)
class FcSpec:
    in_features: int
    out_features: int


@dataclass(frozen=True)
class TruncationPhase:
    phase_id: str
    client_action: str
    shift_bits: int | None
    shape: tuple[int, ...]


@dataclass(frozen=True)
class NetworkTopology:
    network_id: str
    conv: ConvSpec
    pools: tuple[PoolSpec, ...]
    fcs: tuple[FcSpec, ...]
    truncation_phases: tuple[TruncationPhase, ...]


NETWORK_A_TRUNCATION = (
    TruncationPhase("after_conv", "relu", None, (1, 1, 32, 32)),
    TruncationPhase("after_pool", "shift", 26, (1, 64)),
    TruncationPhase("after_fc1", "relu_then_shift", 32, (1, 16)),
    TruncationPhase("after_fc2", "relu_only", None, (1, 10)),
)

NETWORK_B_TRUNCATION = (
    TruncationPhase("after_conv", "relu", None, (1, 1, 32, 32)),
    TruncationPhase("after_pool", "shift", 26, (1, 64)),
    TruncationPhase("after_fc1", "relu_then_shift", 32, (1, 32)),
    TruncationPhase("after_fc2", "relu_only", None, (1, 10)),
)

NETWORK_A = NetworkTopology(
    network_id="A",
    conv=ConvSpec(kernel_h=3, kernel_w=3, in_channels=1, out_channels=1, stride=1, padding=1),
    pools=(PoolSpec(kernel_h=4, kernel_w=4, stride=4),),
    fcs=(
        FcSpec(in_features=64, out_features=16),
        FcSpec(in_features=16, out_features=10),
    ),
    truncation_phases=NETWORK_A_TRUNCATION,
)

NETWORK_B = NetworkTopology(
    network_id="B",
    conv=ConvSpec(kernel_h=3, kernel_w=3, in_channels=1, out_channels=1, stride=1, padding=1),
    pools=(PoolSpec(kernel_h=4, kernel_w=4, stride=4),),
    fcs=(
        FcSpec(in_features=64, out_features=32),
        FcSpec(in_features=32, out_features=10),
    ),
    truncation_phases=NETWORK_B_TRUNCATION,
)


LENET_TRUNCATION = (
    TruncationPhase("after_conv1", "relu_pool_shift", 32, (1, 6, 28, 28)),
    TruncationPhase("after_conv2", "relu_pool_shift", 32, (1, 16, 10, 10)),
    TruncationPhase("after_c3", "relu_then_shift", 32, (1, 120)),
    TruncationPhase("after_fc4", "relu_then_shift", 32, (1, 84)),
    TruncationPhase("after_fc5", "logits_only", None, (1, 10)),
)

LENET_MNIST = NetworkTopology(
    network_id="lenet_mnist",
    conv=ConvSpec(kernel_h=5, kernel_w=5, in_channels=1, out_channels=6, stride=1, padding=0),
    pools=(PoolSpec(kernel_h=2, kernel_w=2, stride=2),),
    fcs=(
        FcSpec(in_features=400, out_features=120),
        FcSpec(in_features=120, out_features=84),
        FcSpec(in_features=84, out_features=10),
    ),
    truncation_phases=LENET_TRUNCATION,
)

LENET_CIFAR = NetworkTopology(
    network_id="lenet_cifar",
    conv=ConvSpec(kernel_h=5, kernel_w=5, in_channels=3, out_channels=6, stride=1, padding=0),
    pools=(PoolSpec(kernel_h=2, kernel_w=2, stride=2),),
    fcs=(
        FcSpec(in_features=400, out_features=120),
        FcSpec(in_features=120, out_features=84),
        FcSpec(in_features=84, out_features=10),
    ),
    truncation_phases=LENET_TRUNCATION,
)


RESNET18_TRUNCATION = (
    TruncationPhase("after_stem",         "relu_then_shift", 32, (1, 64, 32, 32)),
    TruncationPhase("after_l1b0c1",       "relu_then_shift", 32, (1, 64, 32, 32)),
    TruncationPhase("after_l1b0c2",       "relu_then_shift", 32, (1, 64, 32, 32)),
    TruncationPhase("after_l1b1c1",       "relu_then_shift", 32, (1, 64, 32, 32)),
    TruncationPhase("after_l1b1c2",       "relu_then_shift", 32, (1, 64, 32, 32)),
    TruncationPhase("after_l2b0c1",       "relu_then_shift", 32, (1, 128, 16, 16)),
    TruncationPhase("after_l2b0c2",       "relu_then_shift", 32, (1, 128, 16, 16)),
    TruncationPhase("after_l2b1c1",       "relu_then_shift", 32, (1, 128, 16, 16)),
    TruncationPhase("after_l2b1c2",       "relu_then_shift", 32, (1, 128, 16, 16)),
    TruncationPhase("after_l3b0c1",       "relu_then_shift", 32, (1, 256, 8, 8)),
    TruncationPhase("after_l3b0c2",       "relu_then_shift", 32, (1, 256, 8, 8)),
    TruncationPhase("after_l3b1c1",       "relu_then_shift", 32, (1, 256, 8, 8)),
    TruncationPhase("after_l3b1c2",       "relu_then_shift", 32, (1, 256, 8, 8)),
    TruncationPhase("after_l4b0c1",       "relu_then_shift", 32, (1, 512, 4, 4)),
    TruncationPhase("after_l4b0c2",       "relu_then_shift", 32, (1, 512, 4, 4)),
    TruncationPhase("after_l4b1c1",       "relu_then_shift", 32, (1, 512, 4, 4)),
    TruncationPhase("after_l4b1c2",       "relu_then_shift", 32, (1, 512, 4, 4)),
    TruncationPhase("after_pool_linear",  "logits_only",     None, (1, 10)),
)

NETWORK_RESNET18 = NetworkTopology(
    network_id="resnet18_cifar",
    conv=ConvSpec(kernel_h=3, kernel_w=3, in_channels=3, out_channels=64, stride=1, padding=1),
    pools=(PoolSpec(kernel_h=4, kernel_w=4, stride=4),),
    fcs=(FcSpec(in_features=512, out_features=10),),
    truncation_phases=RESNET18_TRUNCATION,
)


def get_topology(network_id: str) -> NetworkTopology:
    key = network_id.upper()
    if key == "A":
        return NETWORK_A
    if key == "B":
        return NETWORK_B
    lkey = network_id.lower().replace("-", "_")
    if lkey == "lenet_mnist":
        return LENET_MNIST
    if lkey in ("lenet_cifar", "lenet_cifar10", "lenet"):
        return LENET_CIFAR
    if lkey in ("resnet18_cifar", "resnet18", "resnet18_cifar10"):
        return NETWORK_RESNET18
    raise KeyError(f"unknown network topology: {network_id}")
