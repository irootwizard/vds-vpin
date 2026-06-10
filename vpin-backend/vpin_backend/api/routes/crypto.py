from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vpin_backend.config import get_settings
from vpin_backend.crypto.ahe import (
    decrypt_ciphertext_pair,
    encrypt_scalar,
    homomorphic_add,
    key_gen,
    load_bsgs_table,
)
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge
from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge
from vpin_backend.crypto.server_crypto.coverage import parse_coverage_from_artifact
from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.protocol.server_inputs import ProveRequest, SetupRequest

router = APIRouter(tags=["crypto"])

_SERVER_CRYPTO_PHASES = frozenset({"setup", "prove-with-challenge"})


def _sample_client_challenge(num_pt_add: int, num_pt_mult: int) -> ClientChallenge:
    """API demo helper — production path uses vpin-client P4 only."""
    return ClientChallenge(
        gamma=secrets.token_hex(32),
        gamma_add=secrets.token_hex(32),
        gamma_mult=secrets.token_hex(32),
        num_pt_add=num_pt_add,
        num_pt_mult=num_pt_mult,
    )
_LEGACY_CP_SNARK_PHASES = frozenset({"setup", "full", "verify", "prove"})


class R4Request(BaseModel):
    network: str | None = None
    num_pt_add: int = 2144
    num_pt_mult: int = 178


@router.get("/ahe/self-test")
def ahe_self_test() -> dict:
    """Round-trip encrypt + homomorphic add + decrypt for small integers."""
    settings = get_settings()
    if not settings.resolved_bsgs_table.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"BSGS table missing: {settings.resolved_bsgs_table}",
        )
    table = load_bsgs_table(settings.resolved_bsgs_table)
    keys = key_gen()
    m1, m2 = 42, 58
    c1a, c2a = encrypt_scalar(
        m1,
        generator=keys.generator,
        public_key=keys.public_key,
        curve_order=keys.curve_order,
    )
    c1b, c2b = encrypt_scalar(
        m2,
        generator=keys.generator,
        public_key=keys.public_key,
        curve_order=keys.curve_order,
    )
    c1s, c2s = homomorphic_add(c1a, c2a, c1b, c2b)
    dec = decrypt_ciphertext_pair(
        keys.private_scalar, c1s, c2s, keys.generator, table
    )
    ok = dec == m1 + m2
    return {
        "ok": ok,
        "expected": m1 + m2,
        "decrypted": int(dec),
        "curve_order": str(keys.curve_order),
    }


@router.get("/server-crypto/status")
def server_crypto_status() -> dict:
    bridge = ServerCryptoBridge()
    settings = get_settings()
    artifact = (
        settings.server_crypto_root / "artifacts" / settings.cp_snark_network_default / "protocol.json"
    )
    return {
        "available": bridge.is_available(),
        "default_network": settings.cp_snark_network_default,
        "artifact_exists": artifact.is_file(),
        "artifact_path": str(artifact) if artifact.is_file() else None,
        "coverage": parse_coverage_from_artifact(artifact) if artifact.is_file() else None,
    }


@router.post("/server-crypto/run/{phase}")
def server_crypto_run(phase: str, network: str | None = None, body: R4Request | None = None) -> dict:
    if phase not in _SERVER_CRYPTO_PHASES:
        raise HTTPException(status_code=400, detail=f"invalid phase; allowed: {sorted(_SERVER_CRYPTO_PHASES)}")
    settings = get_settings()
    net = network or (body.network if body else None) or settings.cp_snark_network_default
    bridge = ServerCryptoBridge()
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="vpin-server-crypto not available")

    if phase == "setup":
        result = bridge.run_setup(SetupRequest(network_id=net))
    else:
        req = body or R4Request(network=net)
        challenge = _sample_client_challenge(req.num_pt_add, req.num_pt_mult)
        result = bridge.run_prove_with_challenge(
            ProveRequest(session_id="api", network_id=net, challenge=challenge)
        )

    if not result.ok:
        raise HTTPException(
            status_code=500,
            detail={"stderr": result.stderr, "stdout": result.stdout},
        )
    coverage = None
    if result.artifact_path:
        coverage = parse_coverage_from_artifact(result.artifact_path)
    return {
        "ok": True,
        "phase": result.phase,
        "network": result.network,
        "summary": result.summary,
        "coverage": coverage,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
        "setup_path": str(result.setup_path) if result.setup_path else None,
    }


@router.post("/server-crypto/r4")
def server_crypto_r4(body: R4Request) -> dict:
    """R4: client γ → server prove (challenge sampled server-side for API demo only)."""
    settings = get_settings()
    net = body.network or settings.cp_snark_network_default
    bridge = ServerCryptoBridge()
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="vpin-server-crypto not available")

    setup = bridge.run_setup(SetupRequest(network_id=net))
    if not setup.ok and not (setup.setup_path and setup.setup_path.is_file()):
        raise HTTPException(status_code=500, detail={"stderr": setup.stderr})

    challenge = _sample_client_challenge(body.num_pt_add, body.num_pt_mult)
    prove = bridge.run_prove_with_challenge(
        ProveRequest(
            session_id="r4",
            network_id=net,
            challenge=challenge,
            setup_artifact=setup.setup_path,
        )
    )
    if not prove.ok:
        raise HTTPException(status_code=500, detail={"stderr": prove.stderr})

    artifact_path = prove.artifact_path
    artifact_data = {}
    if artifact_path and artifact_path.is_file():
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))

    return {
        "ok": True,
        "network": net,
        "challenge": challenge.model_dump(),
        "artifact_path": str(artifact_path) if artifact_path else None,
        "coverage": parse_coverage_from_artifact(artifact_path) if artifact_path else None,
        "proof_coverage": artifact_data.get("proof_coverage"),
    }


@router.get("/cp-snark/status")
def cp_snark_status() -> dict:
    bridge = CpSnarkBridge()
    settings = get_settings()
    artifact = settings.cp_snark_root / "artifacts" / settings.cp_snark_network_default / "protocol.json"
    return {
        "available": bridge.is_available(),
        "default_network": settings.cp_snark_network_default,
        "artifact_exists": artifact.is_file(),
        "artifact_path": str(artifact) if artifact.is_file() else None,
        "deprecated": True,
        "use": "/api/v1/crypto/server-crypto/status",
    }


@router.post("/cp-snark/run/{phase}")
def cp_snark_run(phase: str, network: str | None = None) -> dict:
    if phase not in _LEGACY_CP_SNARK_PHASES:
        raise HTTPException(status_code=400, detail="invalid phase")
    settings = get_settings()
    net = network or settings.cp_snark_network_default
    bridge = CpSnarkBridge()
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="cp-snark-full not available")
    result = bridge.run_phase(net, phase)  # type: ignore[arg-type]
    if not result.ok:
        raise HTTPException(
            status_code=500,
            detail={"stderr": result.stderr, "stdout": result.stdout},
        )
    return {
        "ok": True,
        "phase": result.phase,
        "network": result.network,
        "summary": result.summary,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
        "deprecated": True,
    }
