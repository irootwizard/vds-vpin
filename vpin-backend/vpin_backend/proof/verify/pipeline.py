"""P6 verification pipeline skeleton (opening + scalar + future 蟺_ec / CPS.Ver)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from vpin_backend.protocol.messages import ClientChallenge, ProofBundle
from vpin_backend.proof.verify.stack import ServerLinearProofStack, verify_all_client


@dataclass
class ModelOpening:
    weights: list[int] = field(default_factory=list)
    blind: str = ""


@dataclass
class TraceBundle:
    conv_traces: list[dict[str, Any]] = field(default_factory=list)
    pool_traces: list[dict[str, Any]] = field(default_factory=list)
    fc_traces: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VerifyReport:
    ok: bool
    scalar_ok: bool = False
    opening_ok: bool = False
    ec_ok: Optional[bool] = None
    proof_coverage: str = ""
    detail: str = ""


def _trace_ints(raw: list) -> list[int]:
    mod = 1 << 32
    out: list[int] = []
    for x in raw:
        v = int(x)
        if v < 0:
            v %= mod
        out.append(v)
    return out


def _trace_windows(raw: list) -> list[list[int]]:
    return [_trace_ints(row) for row in raw]


def build_stack_from_traces(traces: TraceBundle, skip_fc: bool = False) -> ServerLinearProofStack:
    """Build M1 stack from trace JSON-shaped dicts (A4-2 export format)."""
    from vpin_backend.proof.verify.conv import ConvLayerProofSpec
    from vpin_backend.proof.verify.fc import FcLayerProofSpec
    from vpin_backend.proof.verify.pool import PoolLayerProofSpec

    stack = ServerLinearProofStack(skip_fc=skip_fc)
    for t in traces.conv_traces:
        stack.conv_layers.append(
            ConvLayerProofSpec(
                filter_flat=_trace_ints(t["filter_flat"]),
                windows=_trace_windows(t["windows"]),
                output_flat=_trace_ints(t["output_flat"]),
            )
        )
    for t in traces.pool_traces:
        sums = t.get("output_sums") or t.get("output_flat", [])
        stack.pool_layers.append(
            PoolLayerProofSpec(
                windows=_trace_windows(t["windows"]),
                output_sums=_trace_ints(sums),
            )
        )
    for t in traces.fc_traces:
        stack.fc_layers.append(
            FcLayerProofSpec(
                inputs=_trace_ints(t["inputs"]),
                weights_in_out=_trace_windows(t["weights_in_out"]),
                bias=_trace_ints(t["bias"]),
                outputs=_trace_ints(t["outputs"]),
            )
        )
    return stack


def verify_session(
    artifacts: ProofBundle,
    opening: ModelOpening,
    challenge: ClientChallenge,
    traces: TraceBundle,
    *,
    skip_fc: bool = False,
    cm_w_point_hex: str = "",
    cm_w_digest_hex: str = "",
    num_weights: int | None = None,
) -> VerifyReport:
    """P6 entry: Pedersen opening + M1 scalar + future EC verify."""
    from vpin_backend.commitment.pedersen import verify_pedersen_open

    coverage = artifacts.proof_coverage or "ec_gadget_only"
    opening_ok = verify_pedersen_open(
        opening,
        cm_w_point_hex=cm_w_point_hex,
        cm_w_digest_hex=cm_w_digest_hex,
        num_weights=num_weights,
    )
    stack = build_stack_from_traces(traces, skip_fc=skip_fc)
    scalar_ok = False
    detail = ""
    try:
        verify_all_client(stack, challenge)
        scalar_ok = True
    except Exception as exc:  # noqa: BLE001 鈥?report path for pipeline skeleton
        detail = str(exc)

    ec_ok: Optional[bool] = None  # wired when client EC verify lands (A5-5)
    ok = opening_ok and scalar_ok
    return VerifyReport(
        ok=ok,
        scalar_ok=scalar_ok,
        opening_ok=opening_ok,
        ec_ok=ec_ok,
        proof_coverage=coverage,
        detail=detail,
    )

