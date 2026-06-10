"""Shared layer-proof metadata (port of layer_proof/common.rs)."""

from __future__ import annotations

from enum import Enum

from vpin_client.protocol.messages import ClientChallenge
from vpin_client.verify.rlc import scalar_from_hex


class LayerProofStage(Enum):
    CONVOLUTION = "convolution"
    AVERAGE_POOLING = "average_pooling"
    FULLY_CONNECTED = "fully_connected"


class ProofCoverage(Enum):
    EC_GADGET_ONLY = "ec_gadget_only"
    CONV_RLC = "conv_rlc"
    POOL_ADD = "pool_add"
    FC_RLC = "fc_rlc"
    SERVER_LINEAR_LAYERS = "server_linear_layers"


def challenge_for_stage(stage: LayerProofStage, ch: ClientChallenge) -> int:
    """Map paper challenges to ClientChallenge fields."""
    if stage is LayerProofStage.CONVOLUTION:
        return scalar_from_hex(ch.gamma)
    if stage is LayerProofStage.AVERAGE_POOLING:
        return scalar_from_hex(ch.gamma_add)
    return scalar_from_hex(ch.gamma_mult)
