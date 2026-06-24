"""Stateless server-side homomorphic step worker (P2 process-pool offload).

Runs the same AheEngine compute as in-process, but inside a worker process so
multiple WebSocket sessions can compute in parallel (pure-Python ecdsa is GIL-bound).

Ciphertexts cross the process boundary as compact ``(x, y)`` integer pairs and are
rebuilt into ``ecdsa`` Points inside the worker. Plaintext semantics are identical to
the in-process path (ElGamal randomness does not affect decrypted values), so results
remain bit-exact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.inference.ahe_engine import AheEngine, EnginePhase
from vpin_backend.inference.homomorphic_network_a import get_op_counters, reset_op_counters
from vpin_backend.models.weights_bundle import load_homomorphic_weights

_CURVE: tuple[Any, int, int, Point, Point] | None = None
_WEIGHTS_CACHE: dict[tuple[str, str], Any] = {}


def _curve() -> tuple[Any, int, int, Point, Point]:
    global _CURVE
    if _CURVE is None:
        _CURVE = curve_e2_info()
    return _CURVE


def _weights(weights_dir: str, network_id: str) -> Any:
    key = (weights_dir, network_id)
    cached = _WEIGHTS_CACHE.get(key)
    if cached is None:
        cached = load_homomorphic_weights(Path(weights_dir), network_id)
        _WEIGHTS_CACHE[key] = cached
    return cached


def _xy_to_points(pack: tuple[tuple[int, ...], list[tuple[int, int]]]) -> np.ndarray:
    shape, flat_xy = pack
    curve = _curve()[0]
    arr = np.empty(len(flat_xy), dtype=object)
    for i, (x, y) in enumerate(flat_xy):
        arr[i] = Point(curve, x, y)
    return arr.reshape(shape)


def points_to_xy(arr: np.ndarray) -> tuple[tuple[int, ...], list[tuple[int, int]]]:
    flat = arr.reshape(-1)
    return arr.shape, [(int(p.x()), int(p.y())) for p in flat]


def worker_step(
    weights_dir: str,
    network_id: str,
    pubkey_xy: tuple[int, int],
    phase_value: str,
    phase_id: str,
    c1_pack: tuple[tuple[int, ...], list[tuple[int, int]]],
    c2_pack: tuple[tuple[int, ...], list[tuple[int, int]]],
) -> dict[str, Any]:
    """Run one homomorphic layer step; returns serialized output + op deltas."""
    curve = _curve()[0]
    pubkey = Point(curve, pubkey_xy[0], pubkey_xy[1])
    weights = _weights(weights_dir, network_id)

    engine = AheEngine.for_network(public_key=pubkey, weights=weights, network_id=network_id)
    engine.phase = EnginePhase(phase_value)

    reset_op_counters()
    c1 = _xy_to_points(c1_pack)
    c2 = _xy_to_points(c2_pack)

    if phase_id == "initial":
        res = engine.bind_initial_ciphertext(c1, c2)
    else:
        res = engine.accept_client_ciphertext(phase_id, c1, c2)

    add, mult = get_op_counters()
    return {
        "out_c1": points_to_xy(res.output_c1),
        "out_c2": points_to_xy(res.output_c2),
        "truncate": (
            res.truncate.phase_id,
            res.truncate.client_action,
            res.truncate.shift_bits,
            res.truncate.shape,
        ),
        "inference_complete": res.inference_complete,
        "add": add,
        "mult": mult,
        "new_phase": engine.phase.value,
    }
