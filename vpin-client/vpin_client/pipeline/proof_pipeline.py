"""Computation proof — Network A only; independent of AHE inference."""

from __future__ import annotations

NETWORK_A_PROOF_MODELS = frozenset(
    {"A", "cnn-mnist-trained", "cnn-mnist-trained-20260622_184254"}
)


def is_network_a_proof_model(model_id: str) -> bool:
    if model_id in NETWORK_A_PROOF_MODELS:
        return True
    return model_id.startswith("cnn-mnist-trained")

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import httpx

from vpin_client.crypto.challenge import sample_challenge
from vpin_client.protocol.messages import ClientChallenge, ProofBundle
from vpin_client.verify.pipeline import ModelOpening, TraceBundle, verify_session

PAPER_PROOF_PT_MUL = 178
PAPER_PROOF_PT_ADD = 2144


@dataclass
class ProofPlanInfo:
    model_id: str
    run_dir: Path
    total_pt_mul: int
    total_pt_add: int
    curve_embed: dict[str, Any]


@dataclass
class ProofSessionResult:
    ok: bool
    challenge: ClientChallenge
    artifact_path: Path | None
    proof_coverage: str
    scalar_trace_digest_hex: str | None
    verify_ok: bool
    detail: str = ""


def _load_traces(run_dir: Path) -> TraceBundle:
    root = run_dir / "proof_artifacts"
    conv = json.loads((root / "conv_trace.json").read_text(encoding="utf-8"))
    pool = json.loads((root / "pool_trace.json").read_text(encoding="utf-8"))
    fc = json.loads((root / "fc_trace.json").read_text(encoding="utf-8"))
    return TraceBundle(conv_traces=[conv], pool_traces=[pool], fc_traces=[fc])


async def fetch_proof_plan(
    backend_http: str,
    model_id: str = "cnn-mnist-trained",
) -> ProofPlanInfo:
    url = f"{backend_http.rstrip('/')}/api/v1/proof/plan"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params={"model_id": model_id})
        resp.raise_for_status()
        data = resp.json()
    return ProofPlanInfo(
        model_id=data["model_id"],
        run_dir=Path(data["run_dir"]),
        total_pt_mul=int(data["schedule"]["total_pt_mul"]),
        total_pt_add=int(data["schedule"]["total_pt_add"]),
        curve_embed=data.get("curve_embed", {}),
    )


async def run_computation_proof(
    backend_http: str,
    *,
    model_id: str = "cnn-mnist-trained",
    network_id: str = "A",
    session_id: str = "",
    challenge: ClientChallenge | None = None,
    verify_locally: bool = True,
) -> ProofSessionResult:
    """Sample γ → POST /proof/prove → optional client M1 verify from run_dir traces."""
    plan = await fetch_proof_plan(backend_http, model_id=model_id)
    ch = challenge or sample_challenge(plan.total_pt_add, plan.total_pt_mul)

    url = f"{backend_http.rstrip('/')}/api/v1/proof/prove"
    payload = {
        "session_id": session_id or "client-proof",
        "model_id": model_id,
        "network_id": network_id,
        "challenge": ch.model_dump(),
    }
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json()
            except json.JSONDecodeError:
                pass
            return ProofSessionResult(
                ok=False,
                challenge=ch,
                artifact_path=None,
                proof_coverage="",
                scalar_trace_digest_hex=None,
                verify_ok=False,
                detail=str(detail),
            )
        prove_data = resp.json()

    artifact_path = (
        Path(prove_data["artifact_path"]) if prove_data.get("artifact_path") else None
    )
    if not artifact_path or not artifact_path.is_file():
        return ProofSessionResult(
            ok=False,
            challenge=ch,
            artifact_path=artifact_path,
            proof_coverage=str(prove_data.get("proof_coverage", "")),
            scalar_trace_digest_hex=prove_data.get("scalar_trace_digest_hex"),
            verify_ok=False,
            detail="server prove ok but artifact missing",
        )

    raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    coverage = str(raw.get("proof_coverage", prove_data.get("proof_coverage", "")))
    digest = raw.get("scalar_trace_digest_hex") or prove_data.get(
        "scalar_trace_digest_hex"
    )

    verify_ok = True
    if verify_locally:
        mo = raw.get("model_opening") or {}
        opening = ModelOpening(
            weights=[int(w) for w in mo.get("weights", [])],
            blind=str(mo.get("blind_hex", "")),
        )
        cm_w = raw.get("model_commitment", {}).get("cm_weights", {})
        bundle = ProofBundle(
            rlc_binding=str(raw.get("rlc_binding", "")),
            proof_coverage=coverage,
            prove_time_ms=int(raw.get("prove_time_ms", 0)),
            trace_digest=digest,
        )
        traces = _load_traces(plan.run_dir)
        report = verify_session(
            bundle,
            opening,
            ch,
            traces,
            cm_w_point_hex=str(cm_w.get("point_hex", "")),
            cm_w_digest_hex=str(cm_w.get("digest_hex", "")),
            num_weights=int(raw.get("model_commitment", {}).get("num_weights", 1219)),
        )
        verify_ok = report.ok
        if not verify_ok:
            return ProofSessionResult(
                ok=False,
                challenge=ch,
                artifact_path=artifact_path,
                proof_coverage=coverage,
                scalar_trace_digest_hex=digest,
                verify_ok=False,
                detail=report.detail or "client verify failed",
            )

    return ProofSessionResult(
        ok=True,
        challenge=ch,
        artifact_path=artifact_path,
        proof_coverage=coverage,
        scalar_trace_digest_hex=digest,
        verify_ok=verify_ok,
    )


def run_computation_proof_sync(
    backend_http: str,
    *,
    model_id: str = "cnn-mnist-trained",
    network_id: str = "A",
    session_id: str = "",
    verify_locally: bool = True,
) -> ProofSessionResult:
    return asyncio.run(
        run_computation_proof(
            backend_http,
            model_id=model_id,
            network_id=network_id,
            session_id=session_id,
            verify_locally=verify_locally,
        )
    )


def _commitments_from_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    mc = raw.get("model_commitment") or {}
    cm_w = mc.get("cm_weights") or {}
    ic = raw.get("input_commitment") or {}
    cm_x = ic.get("cm_public") or {}
    cps = raw.get("cps_commitment") or {}
    return {
        "cm_w_hex": cm_w.get("point_hex"),
        "cm_w_digest_hex": cm_w.get("digest_hex"),
        "cm_x_hex": cm_x.get("point_hex"),
        "cm_x_digest_hex": cm_x.get("digest_hex"),
        "cps_cm_hex": cps.get("poly_comm_hex") or cps.get("cm_hex"),
    }


def proof_result_to_dict(
    result: ProofSessionResult,
    *,
    plan: ProofPlanInfo | None = None,
    artifact_raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = artifact_raw or {}
    commitments = _commitments_from_artifact(raw) if raw else {}
    summary: dict[str, Any] = {
        "ok": result.ok and result.verify_ok,
        "verify_ok": result.verify_ok,
        "proof_coverage": result.proof_coverage,
        "scalar_trace_digest_hex": result.scalar_trace_digest_hex,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
        "gamma_prefix": result.challenge.gamma[:8],
        "detail": result.detail,
        "challenge": result.challenge.model_dump(),
        "commitments": commitments,
        "prove_ms": raw.get("prove_time_ms"),
        **{k: v for k, v in commitments.items() if v},
    }
    if plan is not None:
        summary["total_pt_mul"] = plan.total_pt_mul
        summary["total_pt_add"] = plan.total_pt_add
        summary["n_w"] = 1219
        summary["n2_eq_q1"] = plan.curve_embed.get("n2_eq_q1", True)
        summary["run_dir"] = str(plan.run_dir)
    cm_w = commitments.get("cm_w_hex")
    if cm_w:
        summary["summary"] = {
            "cm_w": cm_w,
            "cm_x": commitments.get("cm_x_hex"),
            "prove_ms": raw.get("prove_time_ms"),
        }
    return summary


async def verify_proof_remote(
    backend_http: str,
    network_id: str = "A",
) -> dict[str, Any]:
    url = f"{backend_http.rstrip('/')}/api/v1/proof/verify"
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(url, params={"network": network_id}, json={})
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json()
            except json.JSONDecodeError:
                pass
            return {"ok": False, "message": str(detail)}
        data = resp.json()
    return {
        "ok": bool(data.get("ok")),
        "message": str(data.get("message", "verify failed")),
        "artifact_path": data.get("artifact_path"),
    }


async def save_proof_artifact_remote(
    backend_http: str,
    dest_path: Path,
    *,
    network_id: str = "A",
    source_path: Path | None = None,
) -> None:
    dest_path = dest_path.expanduser()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path and source_path.is_file():
        dest_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        return
    url = f"{backend_http.rstrip('/')}/api/v1/proof/artifact"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, params={"network": network_id})
        resp.raise_for_status()
        data = resp.json()
    dest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
