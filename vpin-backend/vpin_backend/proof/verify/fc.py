"""Fully-connected scalar verify (paper Eq. 10 RLC-only)."""

from __future__ import annotations

from dataclasses import dataclass

from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.proof.verify.common import LayerProofStage, challenge_for_stage
from vpin_backend.proof.verify.conv import LayerProofError
from vpin_backend.proof.verify.rlc import fc_rlc_left, fc_rlc_right


@dataclass
class FcLayerProofSpec:
    inputs: list[int]
    weights_in_out: list[list[int]]
    bias: list[int]
    outputs: list[int]


def verify_fc_eq10_rlc_only(spec: FcLayerProofSpec, challenge: ClientChallenge) -> None:
    """Compressed RLC (Eq. 10) with verifier 纬鈥?鈥?no per-output eq8."""
    gamma_prime = challenge_for_stage(LayerProofStage.FULLY_CONNECTED, challenge)
    left = fc_rlc_left(spec.outputs, gamma_prime)
    right = fc_rlc_right(
        spec.inputs, spec.weights_in_out, spec.bias, gamma_prime
    )
    if left != right:
        raise LayerProofError(LayerProofStage.FULLY_CONNECTED, "RLC mismatch (eq10)")

