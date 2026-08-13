"""Convolution scalar verify (paper Eq. 9 RLC-only)."""

from __future__ import annotations

from dataclasses import dataclass

from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.proof.verify.common import LayerProofStage, challenge_for_stage
from vpin_backend.proof.verify.rlc import conv_rlc_left, conv_rlc_right


class LayerProofError(Exception):
    def __init__(self, stage: LayerProofStage, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"{stage.value}: {detail}")


@dataclass
class ConvLayerProofSpec:
    filter_flat: list[int]
    windows: list[list[int]]
    output_flat: list[int]


def verify_conv_eq9_rlc_only(
    spec: ConvLayerProofSpec, challenge: ClientChallenge
) -> None:
    """Compressed RLC (Eq. 9) with verifier 纬 鈥?no per-cell eq5 (M1 client path)."""
    gamma = challenge_for_stage(LayerProofStage.CONVOLUTION, challenge)
    left = conv_rlc_left(spec.output_flat, gamma)
    right = conv_rlc_right(spec.filter_flat, spec.windows, gamma)
    if left != right:
        raise LayerProofError(LayerProofStage.CONVOLUTION, "RLC mismatch (eq9)")

