"""Stacked M1 client scalar verification across layers."""

from __future__ import annotations

from dataclasses import dataclass, field

from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.proof.verify.conv import ConvLayerProofSpec, verify_conv_eq9_rlc_only
from vpin_backend.proof.verify.fc import FcLayerProofSpec, verify_fc_eq10_rlc_only
from vpin_backend.proof.verify.pool import PoolLayerProofSpec, verify_pool_eq7


@dataclass
class ServerLinearProofStack:
    conv_layers: list[ConvLayerProofSpec] = field(default_factory=list)
    pool_layers: list[PoolLayerProofSpec] = field(default_factory=list)
    fc_layers: list[FcLayerProofSpec] = field(default_factory=list)
    skip_fc: bool = False


def verify_all_client(stack: ServerLinearProofStack, challenge: ClientChallenge) -> None:
    """Run client-side M1 scalar checks (eq9 / eq7 / eq10 RLC-only)."""
    for spec in stack.conv_layers:
        verify_conv_eq9_rlc_only(spec, challenge)
    for spec in stack.pool_layers:
        verify_pool_eq7(spec)
    if not stack.skip_fc:
        for spec in stack.fc_layers:
            verify_fc_eq10_rlc_only(spec, challenge)

