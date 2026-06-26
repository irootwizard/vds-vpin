"""Micro-benchmark AHE encrypt/decrypt (sequential vs parallel)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from vpin_client.crypto.ahe.codec import decrypt_tensor, encrypt_tensor, load_bsgs_table
from vpin_client.crypto.ahe.curve import key_gen

REPO = Path(__file__).resolve().parents[1]
BSGS = REPO / "src" / "Pre_computed_table" / "table.pickle"


def _bench(label: str, fn) -> float:
    t0 = time.perf_counter()
    fn()
    ms = (time.perf_counter() - t0) * 1000
    print(f"{label}: {ms:.1f} ms")
    return ms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells", type=int, default=1024, help="flat tensor size (default 1024)")
    args = parser.parse_args()
    n = args.cells
    side = int(np.sqrt(n))
    if side * side != n:
        raise SystemExit("--cells must be a perfect square for 2d layout")
    shape = (side, side)

    if not BSGS.is_file():
        raise SystemExit(f"BSGS table missing: {BSGS}")

    keys = key_gen()
    table = load_bsgs_table(BSGS)
    plain = np.arange(n, dtype=np.int32).reshape(shape)

    print(f"shape={shape}, cpus={__import__('os').cpu_count()}")

    c1, c2 = encrypt_tensor(plain, keys, layout="2d", parallel=False)
    _bench("encrypt sequential", lambda: encrypt_tensor(plain, keys, layout="2d", parallel=False))
    _bench("encrypt parallel", lambda: encrypt_tensor(plain, keys, layout="2d", parallel=True))

    _bench(
        "decrypt sequential",
        lambda: decrypt_tensor(
            keys.private_scalar, c1, c2, keys.generator, table, parallel=False
        ),
    )
    _bench(
        "decrypt parallel (threads)",
        lambda: decrypt_tensor(
            keys.private_scalar,
            c1,
            c2,
            keys.generator,
            table,
            parallel=True,
        ),
    )
    _bench(
        "decrypt parallel (process)",
        lambda: decrypt_tensor(
            keys.private_scalar,
            c1,
            c2,
            keys.generator,
            table,
            bsgs_path=BSGS,
            parallel=True,
        ),
    )


if __name__ == "__main__":
    main()
