"""protocol.json parsing helpers for computation proof API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vpin_backend.protocol.messages import ClientChallenge


def load_artifact_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def challenge_wire_from_artifact(artifact: dict[str, Any]) -> dict[str, Any] | None:
    ch = artifact.get("client_challenge")
    if not isinstance(ch, dict):
        return None
    return {
        "gamma": ch.get("gamma", ""),
        "gamma_add": ch.get("gamma_add", ""),
        "gamma_mult": ch.get("gamma_mult", ""),
        "num_pt_add": ch.get("num_pt_add", ch.get("num_point_adds", 0)),
        "num_pt_mult": ch.get("num_pt_mult", ch.get("num_point_mults", 0)),
    }


def challenge_from_artifact(artifact: dict[str, Any]) -> ClientChallenge | None:
    wire = challenge_wire_from_artifact(artifact)
    if wire is None:
        return None
    return ClientChallenge(
        gamma=str(wire["gamma"]),
        gamma_add=str(wire["gamma_add"]),
        gamma_mult=str(wire["gamma_mult"]),
        num_pt_add=int(wire["num_pt_add"]),
        num_pt_mult=int(wire["num_pt_mult"]),
    )


def commitments_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    mc = artifact.get("model_commitment") or {}
    cm_w = mc.get("cm_weights") or {}
    ic = artifact.get("input_commitment") or {}
    cm_x = ic.get("cm_public") or {}
    cps = artifact.get("cps_commitment") or {}
    return {
        "cm_w_hex": cm_w.get("point_hex"),
        "cm_w_digest_hex": cm_w.get("digest_hex"),
        "cm_x_hex": cm_x.get("point_hex"),
        "cm_x_digest_hex": cm_x.get("digest_hex"),
        "cps_cm_hex": cps.get("poly_comm_hex") or cps.get("cm_hex"),
    }
