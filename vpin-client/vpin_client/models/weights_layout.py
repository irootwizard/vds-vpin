"""Weight file layouts per paper CNN network (A–E) for AHE npy bundles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkWeightLayout:
    network_id: str
    weight_fc1: str
    bias_fc1: str
    weight_fc2: str
    bias_fc2: str
    pool_kernel: int = 4
    pool_stride: int = 4
    fc1_in: int = 64
    fc1_out: int = 16
    fc2_out: int = 10
    shift_pool: int = 26
    shift_fc1: int = 32

    @property
    def required_files(self) -> tuple[str, ...]:
        return (self.weight_fc1, self.bias_fc1, self.weight_fc2, self.bias_fc2)

    @property
    def flatten_dim(self) -> int:
        # 32x32 conv+pad -> pool -> flatten
        side = 32 // self.pool_stride
        return side * side * 1


LAYOUTS: dict[str, NetworkWeightLayout] = {
    "A": NetworkWeightLayout(
        network_id="A",
        weight_fc1="weight_fc1_64_16.npy",
        bias_fc1="bias_fc1_16.npy",
        weight_fc2="weight_fc2_16_10.npy",
        bias_fc2="bias_fc2_10.npy",
        fc1_out=16,
    ),
    "B": NetworkWeightLayout(
        network_id="B",
        weight_fc1="weight_fc1_64_32.npy",
        bias_fc1="bias_fc1_32.npy",
        weight_fc2="weight_fc2_32_10.npy",
        bias_fc2="bias_fc2_10.npy",
        fc1_out=32,
    ),
    "C": NetworkWeightLayout(
        network_id="C",
        weight_fc1="weight_fc1_256_16.npy",
        bias_fc1="bias_fc1_16.npy",
        weight_fc2="weight_fc2_16_10.npy",
        bias_fc2="bias_fc2_10.npy",
        pool_kernel=2,
        pool_stride=2,
        fc1_in=256,
        fc1_out=16,
    ),
    "D": NetworkWeightLayout(
        network_id="D",
        weight_fc1="weight_fc1_256_32.npy",
        bias_fc1="bias_fc1_32.npy",
        weight_fc2="weight_fc2_32_10.npy",
        bias_fc2="bias_fc2_10.npy",
        pool_kernel=2,
        pool_stride=2,
        fc1_in=256,
        fc1_out=32,
    ),
    "E": NetworkWeightLayout(
        network_id="E",
        weight_fc1="weight_fc1_256_64.npy",
        bias_fc1="bias_fc1_64.npy",
        weight_fc2="weight_fc2_64_10.npy",
        bias_fc2="bias_fc2_10.npy",
        pool_kernel=2,
        pool_stride=2,
        fc1_in=256,
        fc1_out=64,
    ),
}


def get_layout(network_id: str) -> NetworkWeightLayout:
    key = network_id.upper()
    if key not in LAYOUTS:
        raise KeyError(f"unknown network layout: {network_id}")
    return LAYOUTS[key]
