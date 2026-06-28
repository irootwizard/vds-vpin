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


def get_topology(network_id: str) -> NetworkTopology:
    key = network_id.upper()
    if key == "A":
        return NETWORK_A
    if key == "B":
        return NETWORK_B
    raise KeyError(f"unknown network topology: {network_id}")
