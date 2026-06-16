"""Average pooling scalar verify (paper Eq. 7)."""

from __future__ import annotations

from dataclasses import dataclass

from vpin_client.verify.common import LayerProofStage
from vpin_client.verify.conv import LayerProofError
from vpin_client.verify.rlc import E1_FIELD_MODULUS, embed_u128_to_scalar


@dataclass
class PoolLayerProofSpec:
    windows: list[list[int]]
    output_sums: list[int]


def verify_pool_eq7(spec: PoolLayerProofSpec) -> None:
    """JB = sum of window (homomorphic sum before public scale)."""
    if len(spec.output_sums) != len(spec.windows):
        raise LayerProofError(
            LayerProofStage.AVERAGE_POOLING,
            f"sums {len(spec.output_sums)} vs windows {len(spec.windows)}",
        )
    for i, window in enumerate(spec.windows):
        acc = 0
        for v in window:
            acc = (acc + embed_u128_to_scalar(v)) % E1_FIELD_MODULUS
        expected = embed_u128_to_scalar(spec.output_sums[i])
        if acc != expected:
            raise LayerProofError(
                LayerProofStage.AVERAGE_POOLING,
                f"window {i}: sum != output_sums",
            )
