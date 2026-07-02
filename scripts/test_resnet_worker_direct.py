# -*- coding: utf-8 -*-
"""Direct Rust worker test — bypasses WebSocket to isolate the crash."""
from __future__ import annotations

import json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for sub in ("", "vpin-backend", "vpin-client"):
    p = REPO / sub if sub else REPO
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np
from vpin_backend.crypto.ahe.curve import key_gen, curve_e2_info
from vpin_backend.inference.ahe_worker import (
    ResNetWorkerSession, points_to_xy,
)

# Fake ciphertext: create encrypted zeros at f=16
km = key_gen()
curve, _, _, G, identity = curve_e2_info()

def fake_encrypt(shape, value=0):
    """Create fake ciphertext arrays — NOT real encryption, just point encoding."""
    arr = np.empty(shape, dtype=object)
    flat = arr.reshape(-1)
    for i in range(len(flat)):
        if value == 0 and i == 0:
            flat[i] = identity  # some identity points
        else:
            # Create actual encrypted points
            m = value + (i % 100)  # small plaintext values
            pt = m * G
            flat[i] = pt
    return arr

pk_xy = (int(km.public_key.x()), int(km.public_key.y()))
weights_dir = REPO / "model_training" / "outputs" / "resnet18_20260629_054142"

print(f"[test] weights_dir={weights_dir}")
print(f"[test] pk=({pk_xy[0]}, {pk_xy[1]})")

try:
    rw = ResNetWorkerSession.ensure(str(weights_dir), pk_xy)
    print("[test] WorkerSession created, worker initialized")
except Exception as e:
    print(f"[test] INIT FAILED: {e}")
    sys.exit(1)

# Phase 1: stem conv
# Real client encrypts actual image data. We'll use the real encryption flow.
from vpin_client.crypto.ahe.codec import encrypt_tensor
from vpin_client.protocol.ws_ahe_client import bsgs_table_path, load_bsgs_table
import random as py_random

# Encrypt a simple test input (mimicking RGB image at f=16)
rng = np.random.default_rng(42)
test_input = rng.integers(-1000, 1000, size=(1, 3, 32, 32), dtype=np.int32)
rng_state = py_random.getstate()
enc_c1, enc_c2 = encrypt_tensor(test_input.reshape(-1), km, layout="4d")

# Reshape to 4D numpy object arrays
c1_arr = np.empty((1, 3, 32, 32), dtype=object)
c2_arr = np.empty((1, 3, 32, 32), dtype=object)
c1_arr.flat[:] = enc_c1
c2_arr.flat[:] = enc_c2

for phase_idx in range(3):  # Test first 3 phases
    phase_id = "initial" if phase_idx == 0 else f"phase_{phase_idx}"

    if phase_id == "initial":
        actual_phase = "initial"
    elif phase_idx == 1:
        actual_phase = "after_stem"
    else:
        actual_phase = "after_l1b0c1"

    print(f"\n[test] ===== Phase {phase_idx+1}: {actual_phase} =====")
    t0 = time.perf_counter()

    try:
        res = rw.step(actual_phase, points_to_xy(c1_arr), points_to_xy(c2_arr))
        dt = time.perf_counter() - t0
        print(f"[test] step ok in {dt:.1f}s, shape={res['shape']}, "
              f"add={res.get('add','?')}, mult={res.get('mult','?')}")

        if res.get("truncate"):
            t = res["truncate"]
            print(f"[test]   truncate: phase={t['phase_id']} action={t['client_action']} "
                  f"shape={t['shape']}")

        if res.get("inference_complete"):
            print(f"[test] Inference complete!")
            break

        # Simulate client processing: unpack output, re-encrypt
        from vpin_backend.api.routes.session import _pack_to_points
        out_c1 = _pack_to_points((tuple(res["shape"]), res["out_c1_xy"]))
        out_c2 = _pack_to_points((tuple(res["shape"]), res["out_c2_xy"]))
        print(f"[test]   unpacked shapes: {out_c1.shape}, {out_c2.shape}")

        # Decrypt (real)
        from vpin_client.crypto.ahe.codec import decrypt_tensor
        import asyncio
        loop = asyncio.new_event_loop()
        table = load_bsgs_table(bsgs_table_path())

        dec = decrypt_tensor(
            km.private_scalar, out_c1, out_c2, km.generator, table,
            layout="4d", bsgs_path=bsgs_table_path(),
        )
        print(f"[test]   decrypted: first5={dec.flat[:5].tolist()}, max_abs={int(np.max(np.abs(dec)))}")

        # Apply relu_then_shift (f=32 → f=16)
        relu = np.maximum(dec, 0)
        from vpin_client.crypto.ahe.codec import fixed_point_to_real, real_to_fixed_point
        reals = fixed_point_to_real(relu.astype(np.int64).reshape(-1), 32)
        processed = real_to_fixed_point(reals, 16)
        print(f"[test]   after relu+shift: first5={processed[:5].tolist()}, max_abs={int(np.max(np.abs(processed)))}")

        # Re-encrypt for next phase
        enc_c1, enc_c2 = encrypt_tensor(processed.astype(np.int32), km, layout="4d")
        target_shape = tuple(t["shape"])
        c1_arr = np.empty(target_shape, dtype=object)
        c2_arr = np.empty(target_shape, dtype=object)
        c1_arr.flat[:] = enc_c1
        c2_arr.flat[:] = enc_c2
        print(f"[test]   re-encrypted to shape={target_shape}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[test] PHASE {phase_idx+1} FAILED: {e}")
        break

rw.release()
print("\n[test] Done")
