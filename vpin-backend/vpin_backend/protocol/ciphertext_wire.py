"""Pickle ciphertext chunk wire format (legacy chunk size 30000)."""

from __future__ import annotations

import base64
import pickle
from dataclasses import dataclass, field

import numpy as np

CHUNK_SIZE = 30_000


@dataclass
class ChunkAssembler:
    phase_id: str
    tensor_part: str
    total_chunks: int
    chunks: dict[int, bytes] = field(default_factory=dict)

    def add(self, chunk_index: int, data_b64: str) -> bool:
        self.chunks[chunk_index] = base64.b64decode(data_b64)
        return len(self.chunks) == self.total_chunks

    def decode(self) -> np.ndarray:
        ordered = b"".join(self.chunks[i] for i in range(self.total_chunks))
        return pickle.loads(ordered)


def encode_tensor_chunks(phase_id: str, tensor_part: str, array: np.ndarray) -> list[dict]:
    payload = pickle.dumps(array, protocol=pickle.HIGHEST_PROTOCOL)
    total = (len(payload) + CHUNK_SIZE - 1) // CHUNK_SIZE
    frames: list[dict] = []
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
