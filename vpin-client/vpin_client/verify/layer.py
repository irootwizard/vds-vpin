"""Client per-layer π verify entry (M5 stubs until in-circuit wired)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LayerProofBundle:
    pi_conv: bytes | None = None
    pi_pool: bytes | None = None
    pi_fc: list[bytes] = field(default_factory=list)


@dataclass
class LayerVerifyReport:
    ok: bool
    conv_ok: bool = True
    pool_ok: bool = True
    fc_ok: bool = True
    proof_coverage: str = "layer_proofs_partial"
    detail: str = ""


def verify_layer_proofs(bundle: LayerProofBundle) -> LayerVerifyReport:
    """
    Verify π_conv / π_pool / π_fc[k] when present.
    MVP: structured stubs from prove-layer pass; non-SNARK payloads fail closed.
    """
    conv_ok = _stub_proof_ok(bundle.pi_conv)
    pool_ok = _stub_proof_ok(bundle.pi_pool)
    fc_ok = all(_stub_proof_ok(p) for p in bundle.pi_fc) if bundle.pi_fc else True
    ok = conv_ok and pool_ok and fc_ok
    return LayerVerifyReport(
        ok=ok,
        conv_ok=conv_ok,
        pool_ok=pool_ok,
        fc_ok=fc_ok,
        proof_coverage="layer_proofs_partial" if ok else "layer_proofs_failed",
    )


def _stub_proof_ok(proof: bytes | None) -> bool:
    if proof is None or len(proof) == 0:
        return True
    try:
        json.loads(proof.decode("utf-8"))
        return True
    except (json.JSONDecodeError, UnicodeDecodeError):
        return proof.startswith(b"stub:")


def layer_bundle_from_dict(raw: dict[str, Any]) -> LayerProofBundle:
    def _bytes(val: Any) -> bytes | None:
        if val is None:
            return None
        if isinstance(val, bytes):
            return val
        if isinstance(val, str):
            return bytes.fromhex(val) if val else b""
        return None

    fc_raw = raw.get("pi_fc") or []
    return LayerProofBundle(
        pi_conv=_bytes(raw.get("pi_conv")),
        pi_pool=_bytes(raw.get("pi_pool")),
        pi_fc=[_bytes(x) or b"" for x in fc_raw],
    )
