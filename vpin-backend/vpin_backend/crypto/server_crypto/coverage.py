"""Honest proof_coverage disclosure mapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COVERAGE_LABELS: dict[str, str] = {
    "ec_gadget_only": "EC gadget SNARK only; no MAC/RLC binding",
    "ec_plus_scalar_check": "EC + client γ scalar checks (M1); not in-circuit MAC",
    "ec_plus_l1_binding": "EC + L1 weight binding in R1CS",
    "skeleton_ec_stub": "Server-crypto stub; EC prove not wired",
    "layer_proofs_partial": "Per-layer π partial (M5 in progress)",
    "cps_ver_unified": "Unified CPS.Ver (M-B′ target)",
}


def parse_coverage_from_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"proof_coverage": "unknown", "disclosure": "artifact missing"}
    data = json.loads(path.read_text(encoding="utf-8"))
    code = str(data.get("proof_coverage", "unknown"))
    return {
        "proof_coverage": code,
        "disclosure": COVERAGE_LABELS.get(code, "unlisted coverage — do not claim paper B′"),
        "prove_time_ms": data.get("prove_time_ms"),
        "network": data.get("network"),
    }
