"""WebSocket session: P0–P6 protocol flow (platform §4)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge
from vpin_backend.inference.engine import run_inference_subprocess
from vpin_backend.protocol.messages import (
    ClientChallenge,
    InferenceComplete,
    InputCommitment,
    ModelCommitment,
    ModelSelect,
    PedersenCommitment,
    ProofBundle,
    SessionStart,
    TruncateRequest,
    VerificationReport,
)
from vpin_backend.protocol.server_inputs import ProveRequest, SetupRequest
from vpin_backend.protocol.session import ServerSessionState
from vpin_backend.storage.registry import get_model as registry_get_model

router = APIRouter(tags=["session"])

_sessions: dict[str, ServerSessionState] = {}

_BUILTIN_NETWORK = {"cnn-mnist": "A", "lenet-mnist": "lenet"}


async def _send(ws: WebSocket, msg_type: str, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps({"type": msg_type, **payload}))


def _resolve_network(model_id: str) -> str:
    entry = registry_get_model(model_id)
    if entry and entry.get("network"):
        return str(entry["network"])
    return _BUILTIN_NETWORK.get(model_id, "A")


def _model_commitment_for(network: str, bridge: ServerCryptoBridge) -> ModelCommitment:
    setup = bridge.run_setup(SetupRequest(network_id=network))
    if not setup.ok or not setup.setup_path:
        raise RuntimeError(setup.stderr or "setup failed")
    raw = json.loads(setup.setup_path.read_text(encoding="utf-8"))
    mc = raw["model_commitment"]
    cm = mc["cm_weights"]
    return ModelCommitment(
        cm_W=PedersenCommitment(point_hex=cm["point_hex"], digest_hex=cm["digest_hex"]),
        e2_digest=mc.get("e2_digest_hex"),
        topology_hash=f"network-{network}",
        num_weights=mc.get("num_weights"),
        curve_e2=mc.get("curve_e2"),
    )


@router.websocket("/session/ws")
async def session_ws(ws: WebSocket) -> None:
    await ws.accept()
    session_id = str(uuid.uuid4())
    state = ServerSessionState(session_id=session_id)
    _sessions[session_id] = state
    bridge = ServerCryptoBridge()

    try:
        while True:
            raw = await ws.receive_text()
            frame = json.loads(raw)
            msg_type = frame.get("type", "")

            if msg_type == "SessionStart":
                msg = SessionStart(**{k: v for k, v in frame.items() if k != "type"})
                accept = state.accept(msg)
                await _send(ws, "SessionAccept", accept.model_dump())

            elif msg_type == "ModelSelect":
                msg = ModelSelect(**{k: v for k, v in frame.items() if k != "type"})
                network = _resolve_network(msg.model_id)
                commitment = _model_commitment_for(network, bridge)
                state.bind_model(msg, commitment, network_id=network)
                await _send(ws, "ModelCommitment", commitment.model_dump(by_alias=True))

            elif msg_type == "InputCommitment":
                msg = InputCommitment(**{k: v for k, v in frame.items() if k != "type"})
                state.commit_input(msg)
                await _send(ws, "InputCommitmentAck", {"ok": True})

            elif msg_type == "PublicKey":
                state.start_inference()
                await _send(
                    ws,
                    "TruncateRequest",
                    TruncateRequest(phase_id="conv1", bits=16, shape=[1, 1, 28, 28]).model_dump(),
                )

            elif msg_type == "CiphertextChunkAck":
                inf = run_inference_subprocess(state.network_id)
                complete = state.complete_inference(
                    InferenceComplete(
                        num_pt_add=inf.num_pt_add,
                        num_pt_mult=inf.num_pt_mult,
                        witness_root=str(inf.witness_root) if inf.witness_root else None,
                    )
                )
                await _send(ws, "InferenceComplete", complete.model_dump())

            elif msg_type == "ClientChallenge":
                msg = ClientChallenge(**{k: v for k, v in frame.items() if k != "type"})
                state.receive_challenge(msg)
                prove = bridge.run_prove_with_challenge(
                    ProveRequest(
                        session_id=session_id,
                        network_id=state.network_id,
                        challenge=msg,
                    )
                )
                if not prove.ok or not prove.artifact_path:
                    await _send(ws, "Error", {"message": prove.stderr})
                    continue
                artifact = json.loads(prove.artifact_path.read_text(encoding="utf-8"))
                bundle = ProofBundle(
                    pi_add=None,
                    pi_mult=None,
                    rlc_binding=artifact.get("rlc_binding_hex", ""),
                    proof_coverage=artifact.get("proof_coverage", "skeleton_ec_stub"),
                    prove_time_ms=int(artifact.get("prove_time_ms", 0)),
                )
                state.attach_proof(bundle)
                await _send(ws, "ProofBundle", bundle.model_dump())

            elif msg_type == "VerificationReport":
                report = VerificationReport(
                    session_id=session_id,
                    ok=bool(frame.get("ok")),
                    cm_W=frame.get("cm_W", ""),
                    cm_x=frame.get("cm_x", ""),
                    gamma_prefix=frame.get("gamma_prefix", ""),
                    proof_coverage=frame.get("proof_coverage", ""),
                    message=frame.get("message"),
                )
                await _send(ws, "VerificationReportAck", report.model_dump(by_alias=True))
                state.close()
                break

            else:
                await _send(ws, "Error", {"message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        state.close()
    finally:
        _sessions.pop(session_id, None)
