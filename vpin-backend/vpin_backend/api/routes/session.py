"""Pure AHE WebSocket session (P0–P3, no proof)."""

from __future__ import annotations

import asyncio
import json
import os
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from ecdsa.ellipticcurve import Point
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vpin_backend.config import get_settings
from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.crypto.ahe.topology import get_topology
from vpin_backend.inference.ahe_engine import AheEngine, EngineStepResult
from vpin_backend.inference.ahe_engine_lenet import AheLenetEngine
from vpin_backend.inference.ahe_engine_resnet import AheResnetEngine
from vpin_client.models.weights_layout import is_lenet_cifar, is_resnet
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

# P2: server-side process pool — offloads GIL-bound homomorphic EC compute so
# concurrent WebSocket sessions can run in parallel. Disable with VPIN_AHE_SERVER_POOL=0.
_SERVER_POOL: ProcessPoolExecutor | None = None


def _server_pool_enabled() -> bool:
    return os.environ.get("VPIN_AHE_SERVER_POOL", "1").strip().lower() not in ("0", "false", "no")


def _get_server_pool() -> ProcessPoolExecutor:
    global _SERVER_POOL
    if _SERVER_POOL is None:
        n = int(os.environ.get("VPIN_AHE_SERVER_WORKERS", "0") or 0)
        if n <= 0:
            n = min(3, max(1, (os.cpu_count() or 4) - 1))
        _SERVER_POOL = ProcessPoolExecutor(max_workers=n)
    return _SERVER_POOL


def _pack_to_points(pack: tuple[tuple[int, ...], list[tuple[int, int] | None]]) -> np.ndarray:
    shape, flat = pack
    curve, _, _, _, identity = curve_e2_info()
    arr = np.empty(len(flat), dtype=object)
    for i, xy in enumerate(flat):
        if xy is None:
            arr[i] = identity
        else:
            arr[i] = Point(curve, int(xy[0]), int(xy[1]))
    return arr.reshape(shape)

_BUILTIN_NETWORK = {
    "cnn-mnist": "A",
    "cnn-mnist-b": "B",
    "lenet-mnist": "lenet_mnist",
    "lenet-cifar10": "lenet_cifar",
    "resnet18-cifar10": "resnet18_cifar",
}


class AheEngineLike(Protocol):
    def bind_initial_ciphertext(self, c1: Any, c2: Any) -> EngineStepResult: ...

    def accept_client_ciphertext(self, phase_id: str, c1: Any, c2: Any) -> EngineStepResult: ...


async def _asend(ws: WebSocket, msg_type: str, payload: dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps({"type": msg_type, **payload}))
    except WebSocketDisconnect:
        raise
    except RuntimeError as exc:
        # Starlette/uvicorn after client already closed the socket.
        if "close message has been sent" in str(exc).lower():
            raise WebSocketDisconnect() from exc
        raise


def _is_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, WebSocketDisconnect):
        return True
    if isinstance(exc, RuntimeError) and "close message has been sent" in str(exc).lower():
        return True
    # websockets library may raise ConnectionClosedError or ConnectionClosedOK
    t = type(exc).__name__
    if "ConnectionClosed" in t:
        return True
    return False


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


async def _send_ciphertext(
    ws: WebSocket, phase_id: str, c1: Any, c2: Any, encoding: str = "pickle"
) -> None:
    import sys
    sys.stderr.write(f"[_send_ciphertext] phase_id={phase_id} c1_shape={c1.shape} c2_shape={c2.shape}\n")
    sys.stderr.flush()
    _strip = frozenset(("type", "encoding"))
    for frame in encode_tensor_chunks(phase_id, "c1", c1, encoding):
        await _asend(ws, "CiphertextPayload", {k: v for k, v in frame.items() if k not in _strip})
    for frame in encode_tensor_chunks(phase_id, "c2", c2, encoding):
        await _asend(ws, "CiphertextPayload", {k: v for k, v in frame.items() if k not in _strip})
    sys.stderr.write(f"[_send_ciphertext] done phase_id={phase_id}\n")
    sys.stderr.flush()


def _pair_ready(assemblers: dict[tuple[str, str], ChunkAssembler], phase_id: str) -> bool:
    for part in ("c1", "c2"):
        asm = assemblers.get((phase_id, part))
        if asm is None or len(asm.chunks) != asm.total_chunks:
            return False
    return True


def _decode_pair(
    assemblers: dict[tuple[str, str], ChunkAssembler],
    phase_id: str,
    shape: tuple[int, ...] | None = None,
) -> tuple[Any, Any]:
    return (
        assemblers[(phase_id, "c1")].decode(shape),
        assemblers[(phase_id, "c2")].decode(shape),
    )


async def _advance_engine(
    ws: WebSocket,
    engine: AheEngineLike,
    assemblers: dict[tuple[str, str], ChunkAssembler],
    phase_id: str,
    session_id: str,
    offload: dict[str, Any] | None = None,
    phase_shapes: dict[str, tuple[int, ...]] | None = None,
    client_encoding: str = "pickle",
) -> bool:
    decode_shape = phase_shapes.get(phase_id) if phase_shapes else None
    c1, c2 = _decode_pair(assemblers, phase_id, decode_shape)

    if offload is not None:
        resnet_session = offload.get("resnet_session")
        if resnet_session is not None:
            # ── ResNet Rust subprocess offload ──
            # Run everything in a thread: serialisation (points_to_xy) +
            # Rust-worker pipe I/O + deserialisation (_pack_to_points).
            from vpin_backend.inference.ahe_worker import points_to_xy

            def _resnet_step():
                import traceback as _tb
                try:
                    res = resnet_session.step(
                        phase_id,
                        points_to_xy(c1),
                        points_to_xy(c2),
                    )
                    out_c1 = _pack_to_points(
                        (tuple(res["shape"]), res["out_c1_xy"])
                    )
                    out_c2 = _pack_to_points(
                        (tuple(res["shape"]), res["out_c2_xy"])
                    )
                    return res, out_c1, out_c2
                except Exception:
                    _tb.print_exc()
                    import sys
                    sys.stderr.write(f"[_resnet_step CRASH] phase_id={phase_id}\n")
                    sys.stderr.write(f"  c1 shape={c1.shape} dtype={c1.dtype}\n")
                    sys.stderr.write(f"  c2 shape={c2.shape} dtype={c2.dtype}\n")
                    sys.stderr.flush()
                    raise

            res, out_c1, out_c2 = await asyncio.to_thread(_resnet_step)
            import sys
            sys.stderr.write(f"[_advance_engine] resnet_step ok shape={res['shape']} truncate={res.get('truncate',{}).get('phase_id','?')}\n")
            sys.stderr.flush()
            t = res["truncate"]
            trunc_phase = t["phase_id"]
            trunc_action = t["client_action"]
            trunc_shift = t.get("shift_bits")
            trunc_shape = t["shape"]
            inference_complete = res.get("inference_complete", False)
            offload["add"] = res.get("add", 0)
            offload["mult"] = res.get("mult", 0)
            num_add, num_mult = offload["add"], offload["mult"]
    else:
        if phase_id == "initial":
            result = await asyncio.to_thread(engine.bind_initial_ciphertext, c1, c2)
        else:
            result = await asyncio.to_thread(engine.accept_client_ciphertext, phase_id, c1, c2)
        out_c1, out_c2 = result.output_c1, result.output_c2
        trunc_phase = result.truncate.phase_id
        trunc_action = result.truncate.client_action
        trunc_shift = result.truncate.shift_bits
        trunc_shape = result.truncate.shape
        inference_complete = result.inference_complete
        num_add, num_mult = result.num_pt_add, result.num_pt_mult

    # For relu_pool_shift, the client returns post-pool shape (spatial dims / pool_kernel).
    _POOL_KERNEL = 2  # LeNet 2×2 avg-pool; all current relu_pool_shift phases use this
    if trunc_action == "relu_pool_shift" and len(trunc_shape) == 4:
        b, c, h, w = trunc_shape
        client_recv_shape: tuple[int, ...] = (b, c, h // _POOL_KERNEL, w // _POOL_KERNEL)
    else:
        client_recv_shape = tuple(trunc_shape)

    await _send_ciphertext(ws, trunc_phase, out_c1, out_c2, client_encoding)
    if phase_shapes is not None:
        phase_shapes[trunc_phase] = client_recv_shape

    import sys
    sys.stderr.write(f"[_advance_engine] sending TruncateRequest phase={trunc_phase} action={trunc_action} shape={trunc_shape}\n")
    sys.stderr.flush()

    trunc_req_kwargs: dict[str, Any] = dict(
        phase_id=trunc_phase,
        client_action=trunc_action,
        shift_bits=trunc_shift,
        shape=trunc_shape,
    )
    if trunc_action == "relu_pool_shift":
        trunc_req_kwargs["input_shape"] = list(trunc_shape)
        trunc_req_kwargs["pool_kernel"] = _POOL_KERNEL
    await _asend(
        ws,
        "TruncateRequest",
        TruncateRequest(**trunc_req_kwargs).model_dump(exclude_none=True),
    )
    import sys
    sys.stderr.write(f"[_advance_engine] TruncateRequest sent\n")
    sys.stderr.flush()
    if inference_complete:
        complete = InferenceComplete(
            num_pt_add=num_add,
            num_pt_mult=num_mult,
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
    engine: AheEngineLike | None = None
    weights_dir: Path = get_settings().cnn_networks_dir / "Pre_trained_model"
    network_id: str = "A"
    selected_model_id: str = "cnn-mnist"
    assemblers: dict[tuple[str, str], ChunkAssembler] = {}
    processed_phases: set[str] = set()
    offload_ctx: dict[str, Any] | None = None
    input_shape: tuple[int, ...] | None = None
    phase_shapes: dict[str, tuple[int, ...]] = {}
    client_encoding: str = "pickle"

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
                    input_shape = tuple(msg.shape)
                    phase_shapes["initial"] = input_shape
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
                    from vpin_backend.pipeline.gates import load_deploy_plan, orchestration_from_plan

                    pk = _public_key_point(msg)
                    if is_resnet(network_id):
                        # Route ResNet compute through Rust subprocess worker.
                        if _server_pool_enabled():
                            from vpin_backend.inference.ahe_worker import ResNetWorkerSession
                            pk_xy = (int(pk.x()), int(pk.y()))
                            rw = await asyncio.to_thread(
                                ResNetWorkerSession.ensure, str(weights_dir), pk_xy
                            )
                            offload_ctx = {
                                "resnet_session": rw,
                                "weights_dir": str(weights_dir),
                                "network_id": network_id,
                                "pubkey_xy": pk_xy,
                                "add": 0,
                                "mult": 0,
                            }
                            # Compute happens in the Rust subprocess; the Python
                            # engine is never invoked.  Use a lightweight dummy so
                            # the "engine is None" check passes.
                            engine = True  # type: ignore[assignment]
                        else:
                            hw = load_homomorphic_weights(weights_dir, network_id)
                            engine = AheResnetEngine.for_network(
                                public_key=pk,
                                weights=hw,
                                network_id=network_id,
                            )
                            offload_ctx = None
                    elif is_lenet_cifar(network_id):
                        hw = load_homomorphic_weights(weights_dir, network_id)
                        deploy_plan = load_deploy_plan(weights_dir) or {}
                        orch = orchestration_from_plan(deploy_plan)
                        engine = AheLenetEngine.for_network(
                            public_key=pk,
                            weights=hw,
                            network_id=network_id,
                            skip_return_phases=orch.get("skip_return_phases"),
                        )
                    else:
                        hw = load_homomorphic_weights(weights_dir, network_id)
                        engine = AheEngine.for_network(
                            public_key=pk,
                            weights=hw,
                            network_id=network_id,
                        )
                    assemblers.clear()
                    processed_phases.clear()
                    phase_shapes = {"initial": input_shape} if input_shape else {}
                    client_encoding = "pickle"
                    # P2: enable process-pool offload for ResNet only.
                    if is_resnet(network_id):
                        pass  # handled in PublicKey branch
                    elif is_lenet_cifar(network_id):
                        offload_ctx = None
                    else:
                        offload_ctx = None

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
                    import sys
                    if msg.chunk_index % 50 == 0 or msg.chunk_index == msg.total_chunks - 1:
                        sys.stderr.write(f"[server chunk] {msg.phase_id}/{msg.tensor_part} chunk {msg.chunk_index}/{msg.total_chunks}\n")
                        sys.stderr.flush()

                    # Detect wire encoding from first c1 chunk of first phase.
                    if (
                        msg.chunk_index == 0
                        and msg.tensor_part == "c1"
                        and client_encoding == "pickle"
                        and assemblers[key].is_ahe_v1()
                    ):
                        client_encoding = "ahe-v1"

                    if msg.phase_id in processed_phases:
                        continue
                    if not _pair_ready(assemblers, msg.phase_id):
                        continue

                    processed_phases.add(msg.phase_id)
                    done = await _advance_engine(
                        ws, engine, assemblers, msg.phase_id, session_id,
                        offload_ctx, phase_shapes, client_encoding,
                    )
                    if done:
                        break

                else:
                    await _asend(ws, "Error", {"message": f"unknown type: {msg_type}"})

            except WebSocketDisconnect:
                break
            except Exception as exc:
                import sys
                sys.stderr.write(f"[session_ws CRASH] {type(exc).__name__}: {exc}\n")
                sys.stderr.flush()
                if _is_disconnect_error(exc):
                    break
                traceback.print_exc()
                try:
                    await _asend(ws, "Error", {"message": str(exc)})
                except Exception:
                    break
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        if offload_ctx and offload_ctx.get("resnet_session"):
            offload_ctx["resnet_session"].release()
            offload_ctx = None
