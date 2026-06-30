"""WebSocket AHE inference client (P0–P3)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import websockets

from vpin_client.crypto.ahe.activation import apply_client_action
from vpin_client.crypto.ahe.codec import (
    decrypt_tensor,
    encrypt_tensor,
    fixed_point_to_real,
    load_bsgs_table,
    prewarm_parallel_crypto,
)
from vpin_client.crypto.ahe.curve import KeyMaterial, key_gen
from vpin_client.data.preprocess import compute_input_digest
from vpin_client.protocol.ahe_trace import (
    ciphertext_summary,
    make_trace_step,
    phase_meta,
    tensor_summary,
)
from vpin_client.protocol.ciphertext_wire import ChunkAssembler, encode_tensor_chunks

TraceCallback = Callable[[dict[str, Any]], None]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "Pre_computed_table" / "table.pickle").is_file():
            return parent
    return here.parents[3]


def bsgs_table_path() -> Path:
    return _repo_root() / "src" / "Pre_computed_table" / "table.pickle"


@dataclass
class AheTiming:
    preprocess_ms: float = 0.0
    crypto_infer_ms: float = 0.0
    e2e_post_preprocess_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class AheSessionResult:
    prediction: int
    logits: list[float]
    label: int | None = None
    mnist_index: int | None = None
    input_digest_hex: str = ""
    timing: AheTiming = field(default_factory=AheTiming)
    num_pt_add: int = 0
    num_pt_mult: int = 0


def _layout_for_shape(shape: list[int]) -> str:
    return "4d" if len(shape) == 4 else "2d"


def _pair_ready(assemblers: dict[tuple[str, str], ChunkAssembler], phase_id: str) -> bool:
    for part in ("c1", "c2"):
        asm = assemblers.get((phase_id, part))
        if asm is None or len(asm.chunks) != asm.total_chunks:
            return False
    return True


async def run_ahe_session(
    backend_ws: str,
    model_id: str,
    fixed_int32: np.ndarray,
    *,
    mnist_index: int | None = None,
    label: int | None = None,
    preprocess_ms: float = 0.0,
    on_trace: TraceCallback | None = None,
    keys: KeyMaterial | None = None,
) -> AheSessionResult:
    t_total_start = time.perf_counter()
    t_crypto_start = time.perf_counter()
    digest = compute_input_digest(fixed_int32)
    # P1: reuse a batch-shared keypair when provided; otherwise fresh per session.
    if keys is None:
        keys = key_gen()
    bsgs_path = bsgs_table_path()
    table = load_bsgs_table(bsgs_path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: prewarm_parallel_crypto(bsgs_path))

    def _trace(step: dict[str, Any]) -> None:
        if on_trace:
            on_trace(step)

    assemblers: dict[tuple[str, str], ChunkAssembler] = {}
    pending_truncate: dict | None = None
    prediction = -1
    logits: list[float] = []
    num_pt_add = 0
    num_pt_mult = 0
    done = asyncio.Event()

    async def _send_json(ws: Any, payload: dict) -> None:
        await ws.send(json.dumps(payload))

    async def _send_ciphertext(ws: Any, phase_id: str, c1: np.ndarray, c2: np.ndarray) -> None:
        for part, arr in (("c1", c1), ("c2", c2)):
            for frame in encode_tensor_chunks(phase_id, part, arr):
                await _send_json(ws, frame)

    async def _handle_truncate(ws: Any, frame: dict) -> None:
        nonlocal prediction, logits, pending_truncate
        phase_id = frame["phase_id"]
        if not _pair_ready(assemblers, phase_id):
            pending_truncate = frame
            return
        shape = frame["shape"]
        layout = _layout_for_shape(shape)
        c1_arr = assemblers[(phase_id, "c1")].decode()
        c2_arr = assemblers[(phase_id, "c2")].decode()
        meta = phase_meta(phase_id)
        _trace(
            make_trace_step(
                f"server_ct_{phase_id}",
                category="服务端",
                title=f"{meta['layer']} · 服务端密文输出",
                summary=f"phase={phase_id} shape={shape}",
                detail=ciphertext_summary(
                    c1_arr,
                    c2_arr,
                    phase_id=phase_id,
                    direction="server→client",
                    chunks_c1=assemblers[(phase_id, "c1")].total_chunks,
                    chunks_c2=assemblers[(phase_id, "c2")].total_chunks,
                ),
            )
        )
        dec = await loop.run_in_executor(
            None,
            lambda: decrypt_tensor(
                keys.private_scalar,
                c1_arr,
                c2_arr,
                keys.generator,
                table,
                layout=layout,
                bsgs_path=bsgs_path,
            ),
        )
        action = frame["client_action"]
        shift_bits = frame.get("shift_bits")
        _trace(
            make_trace_step(
                f"client_decrypt_{phase_id}",
                category="客户端",
                title=f"{meta['layer']} · 客户端解密",
                summary=f"action={action}" + (f" shift={shift_bits}" if shift_bits else ""),
                detail={
                    "phase_id": phase_id,
                    "client_action": action,
                    "shift_bits": shift_bits,
                    "decrypted": tensor_summary(dec, name="decrypted", fixed_bits=16),
                    "operation": meta.get("client_op", action),
                },
            )
        )
        if action == "relu_only":
            out = apply_client_action(dec, action)
            logits = fixed_point_to_real(out, 16).flatten().tolist()
            prediction = int(np.argmax(out))
            _trace(
                make_trace_step(
                    f"client_logits_{phase_id}",
                    category="客户端",
                    title="Logits · 最终输出",
                    summary=f"prediction={prediction}",
                    detail={
                        "logits_float": logits,
                        "logits_fixed": tensor_summary(out, name="logits", fixed_bits=16),
                        "argmax": prediction,
                    },
                )
            )
            pending_truncate = None
            return
        if action == "logits_only":
            out = apply_client_action(dec, action)
            logits = fixed_point_to_real(out, 32).flatten().tolist()
            prediction = int(np.argmax(out))
            _trace(
                make_trace_step(
                    f"client_logits_{phase_id}",
                    category="客户端",
                    title="Logits · 最终输出",
                    summary=f"prediction={prediction}",
                    detail={
                        "logits_float": logits,
                        "logits_fixed": tensor_summary(out, name="logits", fixed_bits=32),
                        "argmax": prediction,
                    },
                )
            )
            pending_truncate = None
            return
        processed = apply_client_action(dec, action, shift_bits=shift_bits)
        _trace(
            make_trace_step(
                f"client_action_{phase_id}",
                category="客户端",
                title=f"{meta['layer']} · {action}",
                summary=f"shape={list(processed.shape)}",
                detail={
                    "action": action,
                    "shift_bits": shift_bits,
                    "output": tensor_summary(processed, name="processed", fixed_bits=16),
                },
            )
        )
        enc = await loop.run_in_executor(
            None, lambda: encrypt_tensor(processed, keys, layout=layout)
        )
        _trace(
            make_trace_step(
                f"client_reenc_{phase_id}",
                category="客户端",
                title=f"{meta['layer']} · 重加密回传",
                summary=f"phase={phase_id} → 服务端下一层",
                detail=ciphertext_summary(
                    enc[0],
                    enc[1],
                    phase_id=phase_id,
                    direction="client→server",
                ),
            )
        )
        await _send_ciphertext(ws, phase_id, enc[0], enc[1])
        pending_truncate = None

    async def _process_frame(ws: Any, frame: dict) -> None:
        nonlocal pending_truncate, num_pt_add, num_pt_mult
        msg_type = frame.get("type")

        if msg_type == "SessionAccept":
            _trace(
                make_trace_step(
                    "p0_accept",
                    category="P0",
                    title="SessionAccept",
                    summary=f"session_id={frame.get('session_id', '')[:8]}...",
                    detail=frame,
                )
            )
            return

        if msg_type == "ModelSelectAck":
            phases = frame.get("truncation_plan", {}).get("phases", [])
            _trace(
                make_trace_step(
                    "p1_model_ack",
                    category="P1",
                    title="ModelSelectAck",
                    summary=f"network={frame.get('network_id')} digest={str(frame.get('weights_digest_hex', ''))[:12]}...",
                    detail={
                        "model_id": frame.get("model_id"),
                        "network_id": frame.get("network_id"),
                        "weights_digest_hex": frame.get("weights_digest_hex"),
                        "truncation_plan": phases,
                    },
                )
            )
            return

        if msg_type == "InputDigestAck":
            _trace(
                make_trace_step(
                    "p2_digest_ack",
                    category="P2",
                    title="InputDigestAck",
                    summary="服务端确认输入摘要",
                    detail=frame,
                )
            )
            return

        if msg_type == "CiphertextPayload":
            key = (frame["phase_id"], frame["tensor_part"])
            if key not in assemblers:
                assemblers[key] = ChunkAssembler(
                    frame["phase_id"], frame["tensor_part"], frame["total_chunks"]
                )
            assemblers[key].add(frame["chunk_index"], frame["data_b64"])
            if pending_truncate and _pair_ready(assemblers, pending_truncate["phase_id"]):
                await _handle_truncate(ws, pending_truncate)

        elif msg_type == "TruncateRequest":
            meta = phase_meta(frame["phase_id"])
            _trace(
                make_trace_step(
                    f"truncate_req_{frame['phase_id']}",
                    category="P3",
                    title=f"TruncateRequest · {meta['layer']}",
                    summary=f"{frame['client_action']}" + (
                        f" shift={frame['shift_bits']}" if frame.get("shift_bits") else ""
                    ),
                    detail={
                        "phase_id": frame["phase_id"],
                        "client_action": frame["client_action"],
                        "shift_bits": frame.get("shift_bits"),
                        "shape": frame.get("shape"),
                        "layer": meta.get("layer"),
                        "data_form": meta.get("data_form"),
                    },
                )
            )
            if _pair_ready(assemblers, frame["phase_id"]):
                await _handle_truncate(ws, frame)
            else:
                pending_truncate = frame

        elif msg_type == "InferenceComplete":
            num_pt_add = int(frame.get("num_pt_add", 0))
            num_pt_mult = int(frame.get("num_pt_mult", 0))
            _trace(
                make_trace_step(
                    "inference_complete",
                    category="完成",
                    title="InferenceComplete",
                    summary=f"pt_add={num_pt_add} pt_mult={num_pt_mult}",
                    detail=frame,
                )
            )

        elif msg_type == "SessionEnd":
            _trace(
                make_trace_step(
                    "session_end",
                    category="完成",
                    title="SessionEnd",
                    summary="ok" if frame.get("ok") else "failed",
                    detail=frame,
                )
            )
            done.set()

        elif msg_type == "Error":
            raise RuntimeError(frame.get("message", "server error"))

    async def _reader(ws: Any, inbox: asyncio.Queue) -> None:
        async for raw in ws:
            await inbox.put(json.loads(raw))

    async with websockets.connect(backend_ws, max_size=None, ping_interval=None) as ws:
        inbox: asyncio.Queue = asyncio.Queue()
        reader_task = asyncio.create_task(_reader(ws, inbox))

        await _send_json(
            ws,
            {"type": "SessionStart", "client_version": "vpin-client/0.1.0", "ahe_params_id": "e2-default"},
        )
        _trace(
            make_trace_step(
                "p0_start",
                category="P0",
                title="SessionStart",
                summary="建立 WebSocket 会话",
                detail={"backend": backend_ws, "ahe_params_id": "e2-default"},
            )
        )
        await _send_json(ws, {"type": "ModelSelect", "model_id": model_id})
        _trace(
            make_trace_step(
                "p1_model_select",
                category="P1",
                title="ModelSelect",
                summary=f"model_id={model_id}",
                detail={"model_id": model_id},
            )
        )
        await _send_json(
            ws,
            {
                "type": "InputDigest",
                "input_digest_hex": digest,
                "shape": list(fixed_int32.shape),
                "fixed_point_bits": 16,
                "mnist_index": mnist_index,
            },
        )
        _trace(
            make_trace_step(
                "p2_input_digest",
                category="P2",
                title="InputDigest",
                summary=f"digest={digest[:16]}... shape={list(fixed_int32.shape)}",
                detail={
                    "input_digest_hex": digest,
                    "shape": list(fixed_int32.shape),
                    "fixed_point_bits": 16,
                    "mnist_index": mnist_index,
                    "plain_input": tensor_summary(fixed_int32, name="fixed_int32", fixed_bits=16),
                },
            )
        )
        await _send_json(
            ws,
            {"type": "PublicKey", "h_x": str(keys.public_key.x()), "h_y": str(keys.public_key.y())},
        )
        _trace(
            make_trace_step(
                "p3_public_key",
                category="P3",
                title="PublicKey",
                summary="客户端公钥 h = sk·G",
                detail={
                    "h_x": str(keys.public_key.x()),
                    "h_y": str(keys.public_key.y()),
                    "note": "私钥仅驻留客户端，不经网络传输",
                },
            )
        )

        loop = asyncio.get_running_loop()
        enc = await loop.run_in_executor(
            None, lambda: encrypt_tensor(fixed_int32, keys, layout="4d")
        )
        # Check if server sent an Error while we were encrypting.
        while not inbox.empty():
            early = inbox.get_nowait()
            if early.get("type") == "Error":
                raise RuntimeError(f"server error: {early.get('message', 'unknown')}")
        _trace(
            make_trace_step(
                "p3_encrypt_initial",
                category="客户端",
                title="输入 · ElGamal 加密",
                summary=f"shape={list(fixed_int32.shape)}",
                detail=ciphertext_summary(enc[0], enc[1], phase_id="initial", direction="client→server"),
            )
        )
        await _send_ciphertext(ws, "initial", enc[0], enc[1])

        while not done.is_set():
            frame = await inbox.get()
            await _process_frame(ws, frame)

        reader_task.cancel()

    t_crypto_end = time.perf_counter()
    crypto_ms = (t_crypto_end - t_crypto_start) * 1000
    timing = AheTiming(
        preprocess_ms=preprocess_ms,
        crypto_infer_ms=crypto_ms,
        e2e_post_preprocess_ms=crypto_ms,
        total_ms=preprocess_ms + crypto_ms,
    )

    return AheSessionResult(
        prediction=prediction,
        logits=logits,
        label=label,
        mnist_index=mnist_index,
        input_digest_hex=digest,
        timing=timing,
        num_pt_add=num_pt_add,
        num_pt_mult=num_pt_mult,
    )
