"""Pure AHE WebSocket session (P0–P3, no proof)."""

from __future__ import annotations

import json
import traceback
import uuid
from pathlib import Path
from typing import Any

from ecdsa.ellipticcurve import Point
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vpin_backend.config import get_settings
from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.crypto.ahe.topology import get_topology
from vpin_backend.inference.ahe_engine import AheEngine
from vpin_backend.inference.homomorphic_network_a import load_network_a_weights
from vpin_backend.models.weights_bundle import load_homomorphic_weights, resolve_weights_dir, weights_digest
from vpin_backend.protocol.ciphertext_wire import ChunkAssembler, encode_tensor_chunks
from vpin_backend.protocol.messages import (
    CiphertextPayload,
    InferenceComplete,
    InputDigest,
    InputDigestAck,
    ModelSelect,
    ModelSelectAck,
    PublicKey,
    SessionAccept,
    SessionEnd,
    SessionStart,
    TruncateRequest,
    TruncationPhase,
    TruncationPlan,
)
from vpin_backend.storage.registry import get_model as registry_get_model

router = APIRouter(tags=["session"])

_BUILTIN_NETWORK = {"cnn-mnist": "A", "cnn-mnist-b": "B", "lenet-mnist": "lenet"}


async def _asend(ws: WebSocket, msg_type: str, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps({"type": msg_type, **payload}))


def _resolve_network(model_id: str) -> str:
    entry = registry_get_model(model_id)
    if entry and entry.get("network"):
        return str(entry["network"])
    return _BUILTIN_NETWORK.get(model_id, "A")


def _weights_digest(weights_dir: Path, network: str = "A") -> str:
    return weights_digest(weights_dir, network)


def _public_key_point(msg: PublicKey) -> Point:
    curve, _, _, _, _ = curve_e2_info()
    if msg.h_x is not None and msg.h_y is not None:
        return Point(curve, int(msg.h_x), int(msg.h_y))
    if msg.h and msg.h.startswith("{"):
        data = json.loads(msg.h)
        return Point(curve, int(data["x"]), int(data["y"]))
    raise ValueError("PublicKey requires h_x/h_y")


async def _send_ciphertext(ws: WebSocket, phase_id: str, c1: Any, c2: Any) -> None:
    for frame in encode_tensor_chunks(phase_id, "c1", c1):
        await _asend(ws, "CiphertextPayload", {k: v for k, v in frame.items() if k != "type"})
    for frame in encode_tensor_chunks(phase_id, "c2", c2):
        await _asend(ws, "CiphertextPayload", {k: v for k, v in frame.items() if k != "type"})


def _pair_ready(assemblers: dict[tuple[str, str], ChunkAssembler], phase_id: str) -> bool:
    for part in ("c1", "c2"):
        asm = assemblers.get((phase_id, part))
        if asm is None or len(asm.chunks) != asm.total_chunks:
            return False
    return True


def _decode_pair(assemblers: dict[tuple[str, str], ChunkAssembler], phase_id: str) -> tuple[Any, Any]:
    return assemblers[(phase_id, "c1")].decode(), assemblers[(phase_id, "c2")].decode()


async def _advance_engine(
    ws: WebSocket,
    engine: AheEngine,
    assemblers: dict[tuple[str, str], ChunkAssembler],
    phase_id: str,
    session_id: str,
) -> bool:
    c1, c2 = _decode_pair(assemblers, phase_id)
    if phase_id == "initial":
        result = engine.bind_initial_ciphertext(c1, c2)
    else:
        result = engine.accept_client_ciphertext(phase_id, c1, c2)

    await _send_ciphertext(ws, result.truncate.phase_id, result.output_c1, result.output_c2)
    await _asend(
        ws,
        "TruncateRequest",
        TruncateRequest(
            phase_id=result.truncate.phase_id,
            client_action=result.truncate.client_action,
            shift_bits=result.truncate.shift_bits,
            shape=result.truncate.shape,
        ).model_dump(),
    )
    if result.inference_complete:
        complete = InferenceComplete(
            num_pt_add=result.num_pt_add,
            num_pt_mult=result.num_pt_mult,
            witness_root=None,
        )
        await _asend(ws, "InferenceComplete", complete.model_dump())
        await _asend(ws, "SessionEnd", SessionEnd(session_id=session_id, ok=True).model_dump())
        return True
    return False


@router.websocket("/session/ws")
async def session_ws(ws: WebSocket) -> None:
    await ws.accept()
    session_id = str(uuid.uuid4())
    engine: AheEngine | None = None
    weights_dir: Path = get_settings().cnn_networks_dir / "Pre_trained_model"
    network_id: str = "A"
    selected_model_id: str = "cnn-mnist"
    assemblers: dict[tuple[str, str], ChunkAssembler] = {}
    processed_phases: set[str] = set()

    try:
        while True:
            raw = await ws.receive_text()
            frame = json.loads(raw)
            msg_type = frame.get("type", "")

            try:
                if msg_type == "SessionStart":
                    SessionStart(**{k: v for k, v in frame.items() if k != "type"})
                    accept = SessionAccept(
                        session_id=session_id,
                        server_version="vpin-backend/0.1.0-ahe",
                        model_catalog_epoch="0",
                    )
                    await _asend(ws, "SessionAccept", accept.model_dump())

                elif msg_type == "ModelSelect":
                    msg = ModelSelect(**{k: v for k, v in frame.items() if k != "type"})
                    selected_model_id = msg.model_id
                    network = _resolve_network(msg.model_id)
                    network_id = network
                    topo = get_topology(network)
                    entry = registry_get_model(msg.model_id) or {}
                    weights_dir = resolve_weights_dir(
                        entry,
                        get_settings().cnn_networks_dir / "Pre_trained_model",
                    )
                    from vpin_backend.pipeline.gates import load_deploy_plan

                    deploy_plan = load_deploy_plan(weights_dir) or {}
                    deployable = entry.get("deployable")
                    if deployable is None:
                        deployable = deploy_plan.get("deployable")
                    range_ok = entry.get("range_ok")
                    if range_ok is None:
                        range_ok = deploy_plan.get("range_ok")
                    accuracy_ok = entry.get("accuracy_ok")
                    if accuracy_ok is None:
                        accuracy_ok = deploy_plan.get("accuracy_ok")
                    adapter_id = deploy_plan.get("adapter_id")

                    plan = TruncationPlan(
                        phases=[
                            TruncationPhase(
                                phase_id=p.phase_id,
                                layer=p.client_action,
                                bits=p.shift_bits or 16,
                            )
                            for p in topo.truncation_phases
                        ]
                    )
                    ack = ModelSelectAck(
                        model_id=msg.model_id,
                        network_id=network,
                        topology_hash=f"network-{network}-v1",
                        weights_digest_hex=_weights_digest(weights_dir, network),
                        truncation_plan=plan,
                        deployable=deployable,
                        range_ok=range_ok,
                        accuracy_ok=accuracy_ok,
                        adapter_id=adapter_id,
                    )
                    await _asend(ws, "ModelSelectAck", ack.model_dump())

                elif msg_type == "InputDigest":
                    msg = InputDigest(**{k: v for k, v in frame.items() if k != "type"})
                    from vpin_backend.pipeline.gates import DatasetModelMismatchError
                    from vpin_backend.pipeline.orchestrator import InferenceOrchestrator

                    orch = InferenceOrchestrator(
                        weights_dir=weights_dir,
                        model_id=selected_model_id,
                        network=network_id,
                    )
                    try:
                        pf = orch.preflight(input_shape=msg.shape)
                        if not pf.ok:
                            await _asend(
                                ws,
                                "Error",
                                {"message": "; ".join(pf.errors or ["preflight failed"])},
                            )
                            continue
                    except DatasetModelMismatchError as exc:
                        await _asend(ws, "Error", {"message": str(exc)})
                        continue
                    await _asend(ws, "InputDigestAck", InputDigestAck().model_dump())

                elif msg_type == "PublicKey":
                    msg = PublicKey(**{k: v for k, v in frame.items() if k != "type"})
                    engine = AheEngine.for_network(
                        public_key=_public_key_point(msg),
                        weights=load_homomorphic_weights(weights_dir, network_id),
                        network_id=network_id,
                    )
                    assemblers.clear()
                    processed_phases.clear()

                elif msg_type == "CiphertextPayload":
                    if engine is None:
                        await _asend(ws, "Error", {"message": "PublicKey required before ciphertext"})
                        continue
                    msg = CiphertextPayload(**{k: v for k, v in frame.items() if k != "type"})
                    key = (msg.phase_id, msg.tensor_part)
                    if key not in assemblers:
                        assemblers[key] = ChunkAssembler(
                            msg.phase_id, msg.tensor_part, msg.total_chunks
                        )
                    assemblers[key].add(msg.chunk_index, msg.data_b64)

                    if msg.phase_id in processed_phases:
                        continue
                    if not _pair_ready(assemblers, msg.phase_id):
                        continue

                    processed_phases.add(msg.phase_id)
                    done = await _advance_engine(ws, engine, assemblers, msg.phase_id, session_id)
                    if done:
                        break

                else:
                    await _asend(ws, "Error", {"message": f"unknown type: {msg_type}"})

            except Exception as exc:
                traceback.print_exc()
                await _asend(ws, "Error", {"message": str(exc)})
                break

    except WebSocketDisconnect:
        pass
