"""P6 M1 scalar + Pedersen opening verify (backend-owned, no vpin-client)."""

from __future__ import annotations

import json
from pathlib import Path

from vpin_backend.protocol.messages import ClientChallenge, ProofBundle
from vpin_backend.proof.artifacts import challenge_from_artifact, load_artifact_json
from vpin_backend.proof.verify.pipeline import (
    ModelOpening,
    TraceBundle,
    VerifyReport,
    verify_session,
)


def load_traces_from_run(run_dir: Path) -> TraceBundle:
    """Load conv/pool/fc trace JSON from a training run proof_artifacts/."""
    root = run_dir / "proof_artifacts"
    conv = json.loads((root / "conv_trace.json").read_text(encoding="utf-8"))
    pool = json.loads((root / "pool_trace.json").read_text(encoding="utf-8"))
    fc_path = root / "fc_trace.json"
    fc_traces: list[dict] = []
    if fc_path.is_file():
        fc_raw = json.loads(fc_path.read_text(encoding="utf-8"))
        if isinstance(fc_raw, dict) and "layers" in fc_raw:
            fc_traces = list(fc_raw["layers"])
        elif isinstance(fc_raw, list):
            fc_traces = fc_raw
        else:
            fc_traces = [fc_raw]
    return TraceBundle(conv_traces=[conv], pool_traces=[pool], fc_traces=fc_traces)


def verify_artifact_m1(
    artifact_path: Path,
    *,
    run_dir: Path,
    challenge: ClientChallenge | None = None,
    skip_fc: bool = False,
) -> VerifyReport:
    """Verify protocol.json against run_dir traces (M1 RLC + opening digest)."""
    raw = load_artifact_json(artifact_path)
    ch = challenge or challenge_from_artifact(raw)
    if ch is None:
        return VerifyReport(
            ok=False,
            detail="artifact missing client_challenge",
        )

    mo = raw.get("model_opening") or {}
    opening = ModelOpening(
        weights=[int(w) for w in mo.get("weights", [])],
        blind=str(mo.get("blind_hex", "")),
    )
    mc = raw.get("model_commitment") or {}
    cm_w = mc.get("cm_weights") or {}
    bundle = ProofBundle(
        rlc_binding=str(raw.get("rlc_binding", "")),
        proof_coverage=str(raw.get("proof_coverage", "")),
        prove_time_ms=int(raw.get("prove_time_ms", 0)),
        trace_digest=raw.get("scalar_trace_digest_hex"),
    )
    traces = load_traces_from_run(run_dir)
    if skip_fc and not traces.fc_traces:
        skip_fc = True
    return verify_session(
        bundle,
        opening,
        ch,
        traces,
        skip_fc=skip_fc,
        cm_w_point_hex=str(cm_w.get("point_hex", "")),
        cm_w_digest_hex=str(cm_w.get("digest_hex", "")),
        num_weights=int(mc.get("num_weights", 1219)),
    )
