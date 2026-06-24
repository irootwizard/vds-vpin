"""WebSocket AHE inference client (P0–P3)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
from vpin_client.crypto.ahe.curve import key_gen
from vpin_client.data.preprocess import compute_input_digest
from vpin_client.protocol.ciphertext_wire import ChunkAssembler, encode_tensor_chunks


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
) -> AheSessionResult:
    t_total_start = time.perf_counter()
    t_crypto_start = time.perf_counter()
    digest = compute_input_digest(fixed_int32)
    keys = key_gen()
    bsgs_path = bsgs_table_path()
    table = load_bsgs_table(bsgs_path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: prewarm_parallel_crypto(bsgs_path))

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
        dec = await loop.run_in_executor(
            None,
            lambda: decrypt_tensor(
                keys.private_scalar,
                assemblers[(phase_id, "c1")].decode(),
                assemblers[(phase_id, "c2")].decode(),
                keys.generator,
                table,
                layout=layout,
                bsgs_path=bsgs_path,
            ),
        )
        action = frame["client_action"]
        if action == "relu_only":
            out = apply_client_action(dec, action)
            logits = fixed_point_to_real(out, 16).flatten().tolist()
            prediction = int(np.argmax(out))
            pending_truncate = None
            return
        processed = apply_client_action(dec, action, shift_bits=frame.get("shift_bits"))
        enc = await loop.run_in_executor(
            None, lambda: encrypt_tensor(processed, keys, layout=layout)
        )
        await _send_ciphertext(ws, phase_id, enc[0], enc[1])
        pending_truncate = None

    async def _process_frame(ws: Any, frame: dict) -> None:
        nonlocal pending_truncate, num_pt_add, num_pt_mult
        msg_type = frame.get("type")

        if msg_type in ("SessionAccept", "ModelSelectAck", "InputDigestAck"):
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
            if _pair_ready(assemblers, frame["phase_id"]):
                await _handle_truncate(ws, frame)
            else:
                pending_truncate = frame

        elif msg_type == "InferenceComplete":
            num_pt_add = int(frame.get("num_pt_add", 0))
            num_pt_mult = int(frame.get("num_pt_mult", 0))

        elif msg_type == "SessionEnd":
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
        await _send_json(ws, {"type": "ModelSelect", "model_id": model_id})
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
        await _send_json(
            ws,
            {"type": "PublicKey", "h_x": str(keys.public_key.x()), "h_y": str(keys.public_key.y())},
        )

        loop = asyncio.get_running_loop()
        enc = await loop.run_in_executor(
            None, lambda: encrypt_tensor(fixed_int32, keys, layout="4d")
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
