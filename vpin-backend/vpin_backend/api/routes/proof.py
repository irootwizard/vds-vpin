"""Computation proof API — cp-snark-full + trained run_dir (independent of AHE infer)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vpin_backend.config import get_settings
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge
from vpin_backend.crypto.server_crypto.coverage import parse_coverage_from_artifact
from vpin_backend.proof.artifacts import (
    challenge_wire_from_artifact,
    commitments_from_artifact,
    load_artifact_json,
)
from vpin_backend.proof.ec_witness_bundle import load_ec_witness_from_run
from vpin_backend.proof.m1_verify import verify_artifact_m1
from vpin_backend.proof.registry import (
    load_proof_plan,
    register_proof_plan,
)
from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.protocol.server_inputs import ProveRequest

router = APIRouter(tags=["proof"])

# Ristretto255 scalar field = E2 base field n2 (paper setup)
_E2_BASE = "7237005577332262213973186563042994240857116359379907606001950938285454250989"
_E2_ORDER = "7237005577332262213973186563042994240704759454384003648147593987722918659549"


class ProveBody(BaseModel):
    session_id: str = ""
    model_id: str = "cnn-mnist-trained"
    network_id: str = "A"
    challenge: ClientChallenge
    run_dir: Path | None = None
    schedule_mode: str = "paper_proof"


class M1VerifyBody(BaseModel):
    model_id: str = "cnn-mnist-trained"
    network_id: str = "A"
    run_dir: Path | None = None
    challenge: ClientChallenge | None = None
    skip_fc: bool = False


@router.get("/proof/curve-embed")
def curve_embed() -> dict:
    return {
        "n2": _E2_BASE,
        "q1": _E2_BASE,
        "q2": _E2_ORDER,
        "n2_eq_q1": True,
        "note": "paper arXiv:2411.07468 — E2 base field equals SNARK scalar field",
    }


@router.get("/proof/plan")
def proof_plan(model_id: str = "cnn-mnist-trained", run_dir: Path | None = None) -> dict:
    try:
        plan = load_proof_plan(model_id, run_dir=run_dir)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    artifacts = plan.run_dir / "proof_artifacts"
    manifest_path = artifacts / "proof_manifest.json"
    manifest = {}
    n_w = 1219
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        n_w = int(manifest.get("n_w", n_w))
    fw_path = artifacts / "full_weights.json"
    if fw_path.is_file():
        fw = json.loads(fw_path.read_text(encoding="utf-8"))
        n_w = int(fw.get("num_weights", n_w))

    layers = []
    if plan.witness.manifest:
        for layer in plan.witness.manifest.layers:
            layers.append(
                {
                    "layer_id": layer.layer_id,
                    "kind": layer.kind,
                    "pt_mul_start": layer.pt_mul_start,
                    "pt_mul_end": layer.pt_mul_end,
                    "pt_add_start": layer.pt_add_start,
                    "pt_add_end": layer.pt_add_end,
                }
            )

    return {
        "model_id": plan.model_id,
        "run_dir": str(plan.run_dir),
        "schedule_mode": plan.schedule_mode,
        "topology": {"network": "A", "pool_k": 4, "n_w": n_w},
        "schedule": {
            "total_pt_mul": plan.witness.total_pt_mul,
            "total_pt_add": plan.witness.total_pt_add,
        },
        "layers": layers,
        "witness": {
            "root": str(plan.witness.root),
            "files_ok": plan.witness.root.is_dir(),
        },
        "w_star": {
            "num_weights": n_w,
            "weights_path": str(fw_path) if fw_path.is_file() else None,
        },
        "curve_embed": curve_embed(),
        "proof_artifacts": str(artifacts),
    }


@router.post("/proof/prove")
def proof_prove(body: ProveBody) -> dict:
    bridge = CpSnarkBridge()
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="cp-snark-full not available")

    req = ProveRequest(
        session_id=body.session_id or "proof-api",
        network_id=body.network_id,
        model_id=body.model_id,
        run_dir=body.run_dir,
        schedule_mode=body.schedule_mode,
        challenge=body.challenge,
    )
    result = bridge.run_prove_with_challenge(req)
    if not result.ok:
        raise HTTPException(
            status_code=500,
            detail={"stderr": result.stderr, "stdout": result.stdout},
        )

    coverage = None
    artifact_data: dict = {}
    if result.artifact_path and result.artifact_path.is_file():
        coverage = parse_coverage_from_artifact(result.artifact_path)
        artifact_data = load_artifact_json(result.artifact_path)

    return {
        "ok": True,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
        "summary": result.summary,
        "coverage": coverage,
        "proof_coverage": artifact_data.get("proof_coverage"),
        "scalar_trace_digest_hex": artifact_data.get("scalar_trace_digest_hex"),
        "cps_commitment": artifact_data.get("cps_commitment"),
        "client_challenge": challenge_wire_from_artifact(artifact_data),
        "commitments": commitments_from_artifact(artifact_data),
    }


@router.get("/proof/artifact")
def proof_artifact(network: str = "A") -> dict:
    settings = get_settings()
    artifact = settings.cp_snark_root / "artifacts" / network / "protocol.json"
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail=f"missing {artifact}")
    data = json.loads(artifact.read_text(encoding="utf-8"))
    data["artifact_path"] = str(artifact)
    return data


@router.post("/proof/verify")
def proof_verify(network: str = "A") -> dict:
    bridge = CpSnarkBridge()
    settings = get_settings()
    artifact = settings.cp_snark_root / "artifacts" / network / "protocol.json"
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail=f"missing {artifact}")
    result = bridge.verify_artifact(artifact)
    if not result.ok:
        raise HTTPException(status_code=500, detail={"stderr": result.stderr, "stdout": result.stdout})
    return {
        "ok": True,
        "artifact_path": str(artifact),
        "message": "cp-snark-full verify-file PASSED",
    }


@router.post("/proof/m1-verify")
def proof_m1_verify(body: M1VerifyBody) -> dict:
    """M1 scalar + Pedersen opening verify (backend-owned Python, independent of cp-snark-full)."""
    settings = get_settings()
    artifact = settings.cp_snark_root / "artifacts" / body.network_id / "protocol.json"
    if not artifact.is_file():
        raise HTTPException(status_code=404, detail=f"missing {artifact}")
    try:
        plan = load_proof_plan(body.model_id, run_dir=body.run_dir)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = verify_artifact_m1(
        artifact,
        run_dir=plan.run_dir,
        challenge=body.challenge,
        skip_fc=body.skip_fc,
    )
    if not report.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "scalar_ok": report.scalar_ok,
                "opening_ok": report.opening_ok,
                "proof_coverage": report.proof_coverage,
                "detail": report.detail,
            },
        )
    return {
        "ok": True,
        "scalar_ok": report.scalar_ok,
        "opening_ok": report.opening_ok,
        "proof_coverage": report.proof_coverage,
        "artifact_path": str(artifact),
        "message": "M1 scalar + Pedersen opening PASSED",
    }


@router.post("/proof/register")
def proof_register(model_id: str, run_dir: Path) -> dict:
    """Link AHE model_id to proof run_dir (same training output)."""
    register_proof_plan(model_id, run_dir)
    try:
        bundle = load_ec_witness_from_run(run_dir, model_id=model_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "model_id": model_id,
        "run_dir": str(run_dir.resolve()),
        "ec_witness": str(bundle.root),
        "total_pt_mul": bundle.total_pt_mul,
        "total_pt_add": bundle.total_pt_add,
    }
