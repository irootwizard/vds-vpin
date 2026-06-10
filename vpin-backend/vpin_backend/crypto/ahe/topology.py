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
class NetworkTopology:
    network_id: str
    conv: ConvSpec
    pools: tuple[PoolSpec, ...]
    fcs: tuple[FcSpec, ...]


NETWORK_A = NetworkTopology(
    network_id="A",
    conv=ConvSpec(kernel_h=3, kernel_w=3, in_channels=1, out_channels=1, stride=1, padding=0),
    pools=(PoolSpec(kernel_h=2, kernel_w=2, stride=2),),
    fcs=(
        FcSpec(in_features=16, out_features=10),
        FcSpec(in_features=10, out_features=10),
    ),
)


def get_topology(network_id: str) -> NetworkTopology:
    if network_id.upper() == "A":
        return NETWORK_A
    raise KeyError(f"unknown network topology: {network_id}")
