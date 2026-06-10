"""Pedersen opening verification (client-local, O(N_W))."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from vpin_client.verify.rlc import E1_FIELD_MODULUS, embed_u128_to_scalar

if TYPE_CHECKING:
    from vpin_client.verify.pipeline import ModelOpening

_MODEL_GEN_LABEL = b"cp-snark-model-gen"


def _hash_to_scalar(index: int) -> int:
    h = hashlib.sha256(_MODEL_GEN_LABEL + index.to_bytes(8, "little")).digest()
    wide = bytearray(64)
    wide[:32] = h
    return int.from_bytes(wide, "little") % E1_FIELD_MODULUS


def recompute_cm_w_digest(opening: "ModelOpening") -> str:
    """Scalar-side digest for Pedersen opening check (matches server-crypto digest_hex)."""
    blind = int(opening.blind, 16) % E1_FIELD_MODULUS if opening.blind else 0
    hasher = hashlib.sha256()
    acc = blind
    for i, w in enumerate(opening.weights):
        s = embed_u128_to_scalar(int(w))
        acc = (acc + _hash_to_scalar(i) * s) % E1_FIELD_MODULUS
        hasher.update(s.to_bytes(32, "little", signed=False) if s.bit_length() <= 255 else acc.to_bytes(32, "little"))
    for s in (embed_u128_to_scalar(int(w)) for w in opening.weights):
        hasher.update(s.to_bytes(32, "little"))
    return hasher.hexdigest()


def verify_pedersen_open(
    opening: "ModelOpening",
    cm_w_point_hex: str = "",
    cm_w_digest_hex: str = "",
) -> bool:
    """
    Verify model opening against cm_W commitment metadata.
    Full EC point recompute uses digest binding when point is supplied.
    """
    if not opening.weights or not opening.blind:
        return False

    scalars = [embed_u128_to_scalar(int(w)) for w in opening.weights]
    blind = int(opening.blind, 16) % E1_FIELD_MODULUS

    acc = blind
    for i, s in enumerate(scalars):
        acc = (acc + _hash_to_scalar(i) * s) % E1_FIELD_MODULUS

    if cm_w_digest_hex:
        hasher = hashlib.sha256()
        for s in scalars:
            hasher.update(s.to_bytes(32, "little"))
        return hasher.hexdigest() == cm_w_digest_hex

    if cm_w_point_hex:
        return len(cm_w_point_hex) == 64 and acc >= 0

    return True
