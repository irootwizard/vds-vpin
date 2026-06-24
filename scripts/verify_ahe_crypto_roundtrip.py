#!/usr/bin/env python3
"""Verify AHE encrypt→decrypt roundtrip (no network inference).

Excludes homomorphic FC/conv bugs: only tests ElGamal + BSGS codec layer.
Exit 0 if all checks pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for sub in ("", "vpin-client", "vpin-backend"):
    p = REPO / sub if sub else REPO
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from vpin_client.crypto.ahe.codec import decrypt_tensor, encrypt_tensor, load_bsgs_table
from vpin_client.crypto.ahe.curve import key_gen
from vpin_client.data.preprocess import load_mnist_test
from vpin_client.protocol.ws_ahe_client import bsgs_table_path


def _roundtrip_tensor(
    plain: np.ndarray,
    keys,
    table: dict,
    layout: str,
    label: str,
) -> dict:
    c1, c2 = encrypt_tensor(plain, keys, layout=layout)
    dec = decrypt_tensor(keys.private_scalar, c1, c2, keys.generator, table, layout=layout)
    diff = np.max(np.abs(dec.astype(np.int64) - plain.astype(np.int64)))
    ok = diff == 0
    return {
        "test": label,
        "shape": list(plain.shape),
        "layout": layout,
        "max_diff": int(diff),
        "pass": ok,
    }


def _scalar_samples() -> list[int]:
    rng = np.random.default_rng(42)
    samples = [0, 1, -1, 32767, -32768, 65535, -65536]
    samples.extend(int(x) for x in rng.integers(-500_000, 500_000, size=20))
    return samples


def run_checks(*, mnist_index: int) -> list[dict]:
    keys = key_gen()
    table = load_bsgs_table(bsgs_table_path())
    results: list[dict] = []

    # 1) Scalar roundtrip
    scalar_fail = 0
    for v in _scalar_samples():
        c1, c2 = encrypt_tensor(np.array([[v]], dtype=np.int32), keys, layout="2d")
        out = decrypt_tensor(keys.private_scalar, c1, c2, keys.generator, table, layout="2d")
        if int(out[0, 0]) != v:
            scalar_fail += 1
    results.append(
        {
            "test": "scalar_roundtrip",
            "n": len(_scalar_samples()),
            "failures": scalar_fail,
            "pass": scalar_fail == 0,
        }
    )

    # 2) Random 4d image-shaped tensor (typical activation magnitudes)
    rng = np.random.default_rng(0)
    small_4d = rng.integers(-300_000, 300_000, size=(1, 1, 32, 32), dtype=np.int32)
    results.append(_roundtrip_tensor(small_4d, keys, table, "4d", "random_4d_int32"))

    # 3) Official MNIST preprocessed input (same as AHE session)
    prep = load_mnist_test(mnist_index)
    fixed = prep.fixed_int32.astype(np.int32)
    results.append(_roundtrip_tensor(fixed, keys, table, "4d", f"mnist_index_{mnist_index}"))

    # 4) FC-shaped 2d tensors (after pool / fc layers)
    for shape, name in [((1, 64), "fc_input_64"), ((1, 16), "fc_hidden_16"), ((1, 10), "logits_10")]:
        t = rng.integers(-2_000_000_000, 2_000_000_000, size=shape, dtype=np.int32)
        results.append(_roundtrip_tensor(t, keys, table, "2d", name))

    # 5) Client vs backend codec agreement (same keys, same plaintext)
    from vpin_backend.crypto.ahe.codec import decrypt_tensor as srv_decrypt
    from vpin_backend.crypto.ahe.codec import encrypt_tensor as srv_encrypt

    probe = prep.fixed_int32.astype(np.int32)
    c1c, c2c = encrypt_tensor(probe, keys, layout="4d")
    c1s, c2s = srv_encrypt(probe, keys, layout="4d")
    dec_c = decrypt_tensor(keys.private_scalar, c1c, c2c, keys.generator, table, layout="4d")
    dec_s = srv_decrypt(keys.private_scalar, c1s, c2s, keys.generator, table, layout="4d")
    cross = int(np.max(np.abs(dec_c.astype(np.int64) - dec_s.astype(np.int64))))
    results.append(
        {
            "test": "client_backend_codec_agree",
            "max_diff": cross,
            "pass": cross == 0,
        }
    )

    # 6) Post-FC decrypt magnitudes (>int32) must survive decrypt + TReLU shift (legacy Client.py)
    from vpin_client.crypto.ahe.activation import apply_client_action as client_shift
    from vpin_client.crypto.ahe.codec import to_signed_fixed

    fc1_decrypt = np.array([[42_230_047_542]], dtype=np.int64)
    preserved = int(to_signed_fixed(fc1_decrypt.copy())[0, 0]) == 42_230_047_542
    shifted = client_shift(fc1_decrypt[0], "relu_then_shift", shift_bits=32)
    shift_ok = int(np.abs(shifted).max()) > 600_000  # ~9.8 @ f=16, not ~30k after int32 wrap
    results.append(
        {
            "test": "fc1_decrypt_trelu_shift",
            "preserved_int64": preserved,
            "shifted_max": int(np.abs(shifted).max()),
            "pass": preserved and shift_ok,
        }
    )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="AHE encrypt/decrypt roundtrip verification")
    parser.add_argument("--mnist-index", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        results = run_checks(mnist_index=args.mnist_index)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    all_ok = all(r.get("pass") for r in results)
    if args.json:
        print(json.dumps({"pass": all_ok, "checks": results}, indent=2))
    else:
        for r in results:
            status = "PASS" if r.get("pass") else "FAIL"
            print(f"[{status}] {r}")
        print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
