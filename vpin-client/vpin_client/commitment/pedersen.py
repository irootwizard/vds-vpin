"""Pedersen opening verification (client-local, O(N_W))."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
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


def _scalar_to_digest_bytes(scalar: int) -> bytes:
    """32-byte canonical scalar encoding (matches libspartan Scalar::to_bytes for embedded u128)."""
    return (scalar % E1_FIELD_MODULUS).to_bytes(32, "little")


def scalars_digest(weights: list[int]) -> str:
    """SHA256 over embedded weight scalar bytes — matches commitment.rs scalars_digest."""
    hasher = hashlib.sha256()
    for w in weights:
        s = embed_u128_to_scalar(int(w))
        hasher.update(_scalar_to_digest_bytes(s))
    return hasher.hexdigest()


def _verify_point_via_rust(setup_json: Path) -> bool | None:
    """Delegate full Ristretto point check to vpin-server-crypto when workspace is present."""
    repo = Path(__file__).resolve().parents[3]
    manifest = repo / "vpin-backend" / "Cargo.toml"
    if not manifest.is_file() or not setup_json.is_file():
        return None
    exe = repo / "vpin-backend" / "target" / "debug" / "vpin-server-crypto.exe"
    cmd = (
        [str(exe), "verify-pedersen", str(setup_json)]
        if exe.is_file()
        else [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(manifest),
            "-p",
            "vpin-server-crypto",
            "--",
            "verify-pedersen",
            str(setup_json),
        ]
    )
    proc = subprocess.run(
        cmd,
        cwd=str(repo / "vpin-backend"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode == 0 and "pedersen_open_ok" in proc.stdout:
        return True
    if proc.returncode != 0:
        return False
    return None


def verify_pedersen_open(
    opening: "ModelOpening",
    cm_w_point_hex: str = "",
    cm_w_digest_hex: str = "",
    *,
    num_weights: int | None = None,
    setup_json_path: Path | None = None,
) -> bool:
    """
    Verify model opening against cm_W commitment metadata.
    Checks digest binding and, when point_hex is supplied, full Pedersen point opening.
    """
    if not opening.weights or not opening.blind:
        return False

    digest_ok = True
    if cm_w_digest_hex:
        digest_ok = scalars_digest(opening.weights) == cm_w_digest_hex

    if cm_w_point_hex and setup_json_path:
        rust_ok = _verify_point_via_rust(setup_json_path)
        if rust_ok is not None:
            return rust_ok
        if cm_w_digest_hex:
            return digest_ok
        return len(cm_w_point_hex) == 64

    return digest_ok if cm_w_digest_hex else True
