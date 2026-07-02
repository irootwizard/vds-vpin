"""Ciphertext chunk wire format — pickle (Python client) and ahe-v1 (Rust client)."""

from __future__ import annotations

import base64
import pickle
from dataclasses import dataclass, field

import numpy as np

CHUNK_SIZE = 30_000
AHE_V1_MAGIC = b"ahe1"
_AHE_V1_CELLS_PER_CHUNK = 256


def _is_ahe_v1(raw: bytes) -> bool:
    return len(raw) >= 4 and raw[:4] == AHE_V1_MAGIC


def _decode_ahe_v1_chunks(chunks_data: list[bytes], shape: tuple[int, ...]) -> np.ndarray:
    from ecdsa.ellipticcurve import Point

    from vpin_backend.crypto.ahe.curve import curve_e2_info

    curve, _, _, _, identity = curve_e2_info()
    points: list = []
    for data in chunks_data:
        n = int.from_bytes(data[4:8], "little")
        off = 9
        for _ in range(n):
            x = int.from_bytes(data[off : off + 32], "big")
            y = int.from_bytes(data[off + 32 : off + 64], "big")
            off += 64
            points.append(identity if (x == 0 and y == 0) else Point(curve, x, y))
    arr = np.empty(len(points), dtype=object)
    arr[:] = points
    return arr.reshape(shape)


def _encode_ahe_v1_chunks(
    phase_id: str, tensor_part: str, array: np.ndarray
) -> list[dict]:
    flat = array.reshape(-1)
    n_pts = len(flat)
    total = max(1, (n_pts + _AHE_V1_CELLS_PER_CHUNK - 1) // _AHE_V1_CELLS_PER_CHUNK)
    frames = []
    for ci in range(total):
        pts = flat[ci * _AHE_V1_CELLS_PER_CHUNK : (ci + 1) * _AHE_V1_CELLS_PER_CHUNK]
        payload = bytearray()
        payload.extend(AHE_V1_MAGIC)
        payload.extend(len(pts).to_bytes(4, "little"))
        payload.append(0)  # dtype object
        for p in pts:
            x_val = p.x() if hasattr(p, "x") else None
            if x_val is None:
                payload.extend(bytes(64))  # identity
            else:
                payload.extend(int(x_val).to_bytes(32, "big"))
                payload.extend(int(p.y()).to_bytes(32, "big"))
        frames.append(
            {
                "type": "CiphertextPayload",
                "phase_id": phase_id,
                "tensor_part": tensor_part,
                "chunk_index": ci,
                "total_chunks": total,
                "data_b64": base64.b64encode(bytes(payload)).decode("ascii"),
                "encoding": "ahe-v1",
            }
        )
    return frames


@dataclass
class ChunkAssembler:
    phase_id: str
    tensor_part: str
    total_chunks: int
    chunks: dict[int, bytes] = field(default_factory=dict)

    def add(self, chunk_index: int, data_b64: str) -> bool:
        self.chunks[chunk_index] = base64.b64decode(data_b64)
        return len(self.chunks) == self.total_chunks

    def is_ahe_v1(self) -> bool:
        return _is_ahe_v1(self.chunks.get(0, b""))

    def decode(self, shape: tuple[int, ...] | None = None) -> np.ndarray:
        ordered = [self.chunks[i] for i in range(self.total_chunks)]
        if self.is_ahe_v1():
            if shape is None:
                raise ValueError("shape required to decode ahe-v1 ciphertext")
            return _decode_ahe_v1_chunks(ordered, shape)
        return pickle.loads(b"".join(ordered))


def encode_tensor_chunks(
    phase_id: str,
    tensor_part: str,
    array: np.ndarray,
    encoding: str = "pickle",
) -> list[dict]:
    if encoding == "ahe-v1":
        return _encode_ahe_v1_chunks(phase_id, tensor_part, array)
    payload = pickle.dumps(array, protocol=pickle.HIGHEST_PROTOCOL)
    total = (len(payload) + CHUNK_SIZE - 1) // CHUNK_SIZE
    frames = []
    for idx in range(total):
        chunk = payload[idx * CHUNK_SIZE : (idx + 1) * CHUNK_SIZE]
        frames.append(
            {
                "type": "CiphertextPayload",
                "phase_id": phase_id,
                "tensor_part": tensor_part,
                "chunk_index": idx,
                "total_chunks": total,
                "data_b64": base64.b64encode(chunk).decode("ascii"),
            }
        )
    return frames
