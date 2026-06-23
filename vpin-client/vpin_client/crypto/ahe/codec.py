"""Encrypt / decrypt / fixed-point — semantic port of Client.py."""

from __future__ import annotations

import os
import pickle
import random
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_client.crypto.ahe.curve import KeyMaterial

_PARALLEL_MIN_CELLS = 128
_PARALLEL_MP_MIN_CELLS = 512
_MP_WORKER_TABLE: dict[Any, int] | None = None
_MP_DECRYPT_POOL: ProcessPoolExecutor | None = None
_MP_DECRYPT_POOL_PATH: str | None = None
_DECRYPT_THREADS: ThreadPoolExecutor | None = None
_ENCRYPT_THREADS: ThreadPoolExecutor | None = None


def _parallel_enabled() -> bool:
    return os.environ.get("VPIN_AHE_PARALLEL", "1").strip().lower() not in ("0", "false", "no")


def _mp_worker_init(bsgs_path: str) -> None:
    global _MP_WORKER_TABLE
    _MP_WORKER_TABLE = load_bsgs_table(Path(bsgs_path))


def _mp_worker_decrypt_batch(
    batch: list[tuple[tuple[int, ...], int, Point, Point, Point]],
) -> list[tuple[tuple[int, ...], int]]:
    if _MP_WORKER_TABLE is None:
        raise RuntimeError("BSGS worker table not initialized")
    out: list[tuple[tuple[int, ...], int]] = []
    for idx, private_scalar, c1, c2, generator in batch:
        val = decrypt_ciphertext_pair(private_scalar, c1, c2, generator, _MP_WORKER_TABLE)
        out.append((idx, val))
    return out


def _get_mp_decrypt_pool(bsgs_path: Path) -> ProcessPoolExecutor:
    global _MP_DECRYPT_POOL, _MP_DECRYPT_POOL_PATH
    key = str(bsgs_path.resolve())
    if _MP_DECRYPT_POOL is None or _MP_DECRYPT_POOL_PATH != key:
        if _MP_DECRYPT_POOL is not None:
            _MP_DECRYPT_POOL.shutdown(wait=False, cancel_futures=True)
        n_workers = min(3, max(1, (os.cpu_count() or 4) - 1))
        _MP_DECRYPT_POOL = ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_mp_worker_init,
            initargs=(key,),
        )
        _MP_DECRYPT_POOL_PATH = key
    return _MP_DECRYPT_POOL


def _worker_decrypt_batch(
    batch: list[tuple[tuple[int, ...], int, Point, Point, Point, dict[Any, int]]],
) -> list[tuple[tuple[int, ...], int]]:
    out: list[tuple[tuple[int, ...], int]] = []
    for idx, private_scalar, c1, c2, generator, table in batch:
        val = decrypt_ciphertext_pair(private_scalar, c1, c2, generator, table)
        out.append((idx, val))
    return out


def _worker_encrypt_batch(
    batch: list[tuple[tuple[int, ...], int, Point, Point, int]],
) -> list[tuple[tuple[int, ...], Point, Point]]:
    out: list[tuple[tuple[int, ...], Point, Point]] = []
    for idx, val, generator, public_key, curve_order in batch:
        c1, c2 = encrypt_scalar(
            int(val),
            generator=generator,
            public_key=public_key,
            curve_order=curve_order,
        )
        out.append((idx, c1, c2))
    return out


def _pool_workers() -> int:
    return min(8, max(2, os.cpu_count() or 4))


def _batched(items: list, batch_size: int) -> list[list]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _get_decrypt_pool() -> ThreadPoolExecutor:
    global _DECRYPT_THREADS
    if _DECRYPT_THREADS is None:
        _DECRYPT_THREADS = ThreadPoolExecutor(max_workers=_pool_workers())
    return _DECRYPT_THREADS


def _get_encrypt_pool() -> ThreadPoolExecutor:
    global _ENCRYPT_THREADS
    if _ENCRYPT_THREADS is None:
        _ENCRYPT_THREADS = ThreadPoolExecutor(max_workers=_pool_workers())
    return _ENCRYPT_THREADS


def real_to_fixed_point(values: np.ndarray, bits: int = 16) -> np.ndarray:
    scale = 2**bits
    return (values * scale).astype(np.int32)


def fixed_point_to_real(values: np.ndarray, bits: int) -> np.ndarray:
    scale = 2**bits
    return np.array(values, dtype=np.float32) / scale


def encrypt_scalar(
    plaintext: int,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[Point, Point]:
    r = random.randrange(1, curve_order - 1)
    m = int(plaintext)
    c1 = r * generator
    c2 = m * generator + r * public_key
    return c1, c2


def _encrypt_sequential(
    tensor: np.ndarray,
    keys: KeyMaterial,
    layout: str,
) -> tuple[np.ndarray, np.ndarray]:
    if layout == "4d":
        shape = tensor.shape
        c1 = np.empty(shape, dtype=object)
        c2 = np.empty(shape, dtype=object)
        for i in range(shape[0]):
            for j in range(shape[1]):
                for k in range(shape[2]):
                    for l in range(shape[3]):
                        c1[i, j, k, l], c2[i, j, k, l] = encrypt_scalar(
                            int(tensor[i, j, k, l]),
                            generator=keys.generator,
                            public_key=keys.public_key,
                            curve_order=keys.curve_order,
                        )
    else:
        rows, cols = tensor.shape
        c1 = np.empty((rows, cols), dtype=object)
        c2 = np.empty((rows, cols), dtype=object)
        for i in range(rows):
            for j in range(cols):
                c1[i, j], c2[i, j] = encrypt_scalar(
                    int(tensor[i, j]),
                    generator=keys.generator,
                    public_key=keys.public_key,
                    curve_order=keys.curve_order,
                )
    return c1, c2


def _encrypt_parallel(
    tensor: np.ndarray,
    keys: KeyMaterial,
    layout: str,
) -> tuple[np.ndarray, np.ndarray]:
    shape = tensor.shape
    c1 = np.empty(shape, dtype=object)
    c2 = np.empty(shape, dtype=object)
    tasks = [
        (
            idx,
            int(tensor[idx]),
            keys.generator,
            keys.public_key,
            keys.curve_order,
        )
        for idx in np.ndindex(shape)
    ]
    n_workers = _pool_workers()
    batch_size = max(16, len(tasks) // (n_workers * 2))
    batches = _batched(tasks, batch_size)
    pool = _get_encrypt_pool()
    for batch_results in pool.map(_worker_encrypt_batch, batches):
        for idx, c1p, c2p in batch_results:
            c1[idx] = c1p
            c2[idx] = c2p
    return c1, c2


def encrypt_tensor(
    tensor: np.ndarray,
    keys: KeyMaterial,
    layout: str = "4d",
    *,
    parallel: bool | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    use_parallel = _parallel_enabled() if parallel is None else parallel
    n_cells = int(np.prod(tensor.shape))
    if use_parallel and n_cells >= _PARALLEL_MIN_CELLS:
        return _encrypt_parallel(tensor, keys, layout)
    return _encrypt_sequential(tensor, keys, layout)


def _giant_step(alpha: Point, beta: Point, beta_neg: Point, table: dict) -> int:
    m = 3_200_000
    inv_alpha_m = -m * alpha
    gamma = beta
    gamma2 = beta_neg
    for i in range(m):
        key = (gamma.x(), gamma.y())
        if key in table:
            return i * m + table[key]
        key2 = (gamma2.x(), gamma2.y())
        if key2 in table:
            return -(i * m + table[key2])
        gamma = gamma + inv_alpha_m
        gamma2 = gamma2 + inv_alpha_m
    raise ValueError("discrete log not found in BSGS table range")


def decrypt_ciphertext_pair(
    private_scalar: int,
    c1: Point,
    c2: Point,
    generator: Point,
    table: dict,
) -> int:
    s = private_scalar * c1
    output = c2 + ((-1) * s)
    s2 = private_scalar * ((-1) * c1)
    output2 = ((-1) * c2) + ((-1) * s2)
    return _giant_step(generator, output, output2, table)


def to_signed_fixed(values: np.ndarray) -> np.ndarray:
    """Return decrypted discrete-log integers as int64 (legacy Client.py — no pre-shift int32 cast)."""
    return values.astype(np.int64, copy=False)


def _decrypt_sequential(
    private_scalar: int,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    generator: Point,
    table: dict,
) -> np.ndarray:
    out = np.zeros(enc_c1.shape, dtype=np.int64)
    for idx in np.ndindex(enc_c1.shape):
        out[idx] = decrypt_ciphertext_pair(
            private_scalar,
            enc_c1[idx],
            enc_c2[idx],
            generator,
            table,
        )
    return to_signed_fixed(out)


def _decrypt_parallel(
    private_scalar: int,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    generator: Point,
    table: dict,
) -> np.ndarray:
    out = np.zeros(enc_c1.shape, dtype=np.int64)
    tasks = [
        (idx, private_scalar, enc_c1[idx], enc_c2[idx], generator, table)
        for idx in np.ndindex(enc_c1.shape)
    ]
    n_workers = _pool_workers()
    batch_size = max(16, len(tasks) // (n_workers * 2))
    batches = _batched(tasks, batch_size)
    pool = _get_decrypt_pool()
    for batch_results in pool.map(_worker_decrypt_batch, batches):
        for idx, val in batch_results:
            out[idx] = val
    return to_signed_fixed(out)


def _decrypt_parallel_mp(
    private_scalar: int,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    generator: Point,
    bsgs_path: Path,
) -> np.ndarray:
    out = np.zeros(enc_c1.shape, dtype=np.int64)
    tasks = [
        (idx, private_scalar, enc_c1[idx], enc_c2[idx], generator)
        for idx in np.ndindex(enc_c1.shape)
    ]
    n_workers = min(3, max(1, (os.cpu_count() or 4) - 1))
    batch_size = max(32, len(tasks) // (n_workers * 2))
    batches = _batched(tasks, batch_size)
    pool = _get_mp_decrypt_pool(bsgs_path)
    for batch_results in pool.map(_mp_worker_decrypt_batch, batches):
        for idx, val in batch_results:
            out[idx] = val
    return to_signed_fixed(out)


def decrypt_tensor(
    private_scalar: int,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    generator: Point,
    table: dict,
    layout: str = "2d",
    *,
    bsgs_path: Path | None = None,
    parallel: bool | None = None,
) -> np.ndarray:
    del layout  # kept for API compatibility
    use_parallel = _parallel_enabled() if parallel is None else parallel
    n_cells = int(np.prod(enc_c1.shape))
    if use_parallel and n_cells >= _PARALLEL_MP_MIN_CELLS and bsgs_path is not None:
        return _decrypt_parallel_mp(private_scalar, enc_c1, enc_c2, generator, bsgs_path)
    if use_parallel and n_cells >= _PARALLEL_MIN_CELLS:
        return _decrypt_parallel(private_scalar, enc_c1, enc_c2, generator, table)
    return _decrypt_sequential(private_scalar, enc_c1, enc_c2, generator, table)


_BSGS_CACHE: dict[str, dict[Any, int]] = {}


def prewarm_parallel_crypto(bsgs_path: Path) -> None:
    """Spawn decrypt worker processes early so the first large tensor decrypt avoids cold-start."""
    if _parallel_enabled():
        _get_mp_decrypt_pool(bsgs_path)


def load_bsgs_table(path: Path) -> dict[Any, int]:
    key = str(path.resolve())
    cached = _BSGS_CACHE.get(key)
    if cached is not None:
        return cached
    with path.open("rb") as f:
        table = pickle.load(f)
    _BSGS_CACHE[key] = table
    return table
