#!/usr/bin/env python3
"""ResNet18 WebSocket E2E test — full 18-phase cycle with client-side decrypt/truncate/re-encrypt."""
from __future__ import annotations

import asyncio, json, sys, time, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for sub in ("", "vpin-backend", "vpin-client"):
    p = REPO / sub if sub else REPO
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

WS_URI = "ws://127.0.0.1:8000/api/v1/session/ws"


async def run_full_session():
    import numpy as np
    import websockets
    from vpin_backend.crypto.ahe.curve import key_gen
    from vpin_client.protocol.ws_ahe_client import (
        ChunkAssembler,
        encode_tensor_chunks,
        apply_client_action,
    )
    from vpin_client.crypto.ahe.codec import encrypt_tensor, decrypt_tensor, load_bsgs_table
    from vpin_client.protocol.ws_ahe_client import bsgs_table_path

    async with websockets.connect(WS_URI, ping_interval=None, close_timeout=600, max_size=None) as ws:
        # 1. SessionStart
        await ws.send(json.dumps({"type": "SessionStart", "client_version": "vpin-client/0.1.0"}))
        resp = json.loads(await ws.recv())
        assert resp["type"] == "SessionAccept", f"Expected SessionAccept, got {resp}"
        print(f"[1] SessionAccept OK")

        # 2. ModelSelect
        await ws.send(json.dumps({
            "type": "ModelSelect", "model_id": "resnet18-cifar10",
            "weights_dir": "", "format_adapter_id": "",
        }))
        resp = json.loads(await ws.recv())
        assert resp["type"] == "ModelSelectAck"
        phases = resp.get("truncation_plan", {}).get("phases", [])
        print(f"[2] ModelSelectAck OK  network={resp.get('network_id')}  phases={len(phases)}")

        # 3. InputDigest
        dummy_input = np.zeros((1, 3, 32, 32), dtype=np.int32)
        dummy_input[0, 0, 15, 15] = 1 << 14
        digest = hashlib.sha256(dummy_input.tobytes()).hexdigest()
        await ws.send(json.dumps({
            "type": "InputDigest", "input_digest_hex": digest,
            "shape": [1, 3, 32, 32], "fixed_point_bits": 16,
        }))
        resp = json.loads(await ws.recv())
        if resp["type"] == "Error":
            print(f"[3] InputDigest ERROR: {resp.get('message')}"); return
        assert resp["type"] == "InputDigestAck"
        print(f"[3] InputDigestAck OK")

        # 4. PublicKey + encrypt input
        km = key_gen()
        pk_x, pk_y = str(km.public_key.x()), str(km.public_key.y())
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "PublicKey", "h_x": pk_x, "h_y": pk_y}))

        loop = asyncio.get_running_loop()
        bsgs_path = bsgs_table_path()
        table = await loop.run_in_executor(None, lambda: load_bsgs_table(bsgs_path))
        enc = await loop.run_in_executor(None, lambda: encrypt_tensor(dummy_input, km, layout="4d"))

        assemblers: dict[tuple[str, str], ChunkAssembler] = {}
        for part, arr in (("c1", enc[0]), ("c2", enc[1])):
            for frame in encode_tensor_chunks("initial", part, arr):
                await ws.send(json.dumps(frame))
        print(f"[4] PublicKey + initial ciphertext sent (dt={time.perf_counter()-t0:.1f}s)")

        # 5. Phase loop
        phase_count = 0
        pending_truncate = None

        def _pair_ready(pid: str) -> bool:
            for p in ("c1", "c2"):
                a = assemblers.get((pid, p))
                if a is None or len(a.chunks) != a.total_chunks:
                    return False
            return True

        async def handle_truncate(frame: dict) -> None:
            nonlocal pending_truncate
            pid = frame["phase_id"]
            if not _pair_ready(pid):
                pending_truncate = frame
                return
            shape = frame["shape"]
            c1_arr = assemblers[(pid, "c1")].decode()
            c2_arr = assemblers[(pid, "c2")].decode()
            action = frame["client_action"]
            shift_bits = frame.get("shift_bits")

            dec = await loop.run_in_executor(
                None, lambda: decrypt_tensor(
                    km.private_scalar, c1_arr, c2_arr, km.generator, table,
                    layout="4d" if len(shape) == 4 else "2d", bsgs_path=bsgs_path,
                )
            )

            if action in ("relu_only", "logits_only"):
                out = apply_client_action(dec, action)
                print(f"      FINAL {action}: prediction={int(np.argmax(out))}")
                pending_truncate = None
                return

            processed = apply_client_action(dec, action, shift_bits=shift_bits)
            enc_out = await loop.run_in_executor(
                None, lambda: encrypt_tensor(processed, km, layout="4d" if len(shape) == 4 else "2d")
            )
            for part, arr in (("c1", enc_out[0]), ("c2", enc_out[1])):
                for f in encode_tensor_chunks(pid, part, arr):
                    await ws.send(json.dumps(f))
            pending_truncate = None

        done = False
        while not done:
            raw = await ws.recv()
            frame = json.loads(raw)
            t = frame.get("type", "")

            if t == "CiphertextPayload":
                key = (frame["phase_id"], frame["tensor_part"])
                if key not in assemblers:
                    assemblers[key] = ChunkAssembler(frame["phase_id"], frame["tensor_part"], frame["total_chunks"])
                assemblers[key].add(frame["chunk_index"], frame["data_b64"])

                if frame["chunk_index"] == frame["total_chunks"] - 1:
                    pid = frame["phase_id"]
                    if _pair_ready(pid):
                        phase_count += 1
                        c1n = assemblers[(pid, "c1")].total_chunks
                        print(f"      [{phase_count}] phase={pid}  c1={c1n}chunks  elapsed={time.perf_counter()-t0:.1f}s")
                if pending_truncate and _pair_ready(pending_truncate["phase_id"]):
                    await handle_truncate(pending_truncate)

            elif t == "TruncateRequest":
                pid = frame["phase_id"]
                action = frame["client_action"]
                bits = frame.get("shift_bits")
                shape = frame.get("shape")
                print(f"      TRUNCATE {pid}  action={action}  bits={bits}  shape={shape}")
                if _pair_ready(pid):
                    await handle_truncate(frame)
                else:
                    pending_truncate = frame

            elif t == "InferenceComplete":
                total_dt = time.perf_counter() - t0
                print(f"\n[5] InferenceComplete!  phases={phase_count}  "
                      f"add={frame.get('num_pt_add','?')}  mult={frame.get('num_pt_mult','?')}  "
                      f"total={total_dt:.1f}s")
                done = True

            elif t == "Error":
                print(f"ERROR: {frame.get('message', '?')}"); return

        print("SUCCESS: full ResNet18 WS session completed!")


if __name__ == "__main__":
    asyncio.run(run_full_session())
