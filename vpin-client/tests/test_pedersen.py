"""Pedersen opening verification against server-crypto artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vpin_client.commitment.pedersen import scalars_digest, verify_pedersen_open
from vpin_client.verify.pipeline import ModelOpening

REPO = Path(__file__).resolve().parents[2]
SETUP = (
    REPO
    / "vpin-backend"
    / "crates"
    / "vpin-server-crypto"
    / "artifacts"
    / "A"
    / "setup.json"
)


@pytest.fixture(scope="module")
def setup_artifact() -> dict:
    if not SETUP.is_file():
        bridge_manifest = REPO / "vpin-backend" / "Cargo.toml"
        if not bridge_manifest.is_file():
            pytest.skip("vpin-server-crypto workspace missing")
        proc = subprocess.run(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(bridge_manifest),
                "-p",
                "vpin-server-crypto",
                "--",
                "setup",
                "A",
            ],
            cwd=str(REPO / "vpin-backend"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode != 0:
            pytest.skip(f"setup failed: {proc.stderr}")
    return json.loads(SETUP.read_text(encoding="utf-8"))


def test_scalars_digest_small_weights() -> None:
    d = scalars_digest([1, 2, 3, 42])
    assert len(d) == 64


def test_pedersen_open_roundtrip(setup_artifact: dict) -> None:
    opening_raw = setup_artifact["model_opening"]
    mc = setup_artifact["model_commitment"]["cm_weights"]
    opening = ModelOpening(
        weights=[int(w) for w in opening_raw["weights"]],
        blind=opening_raw["blind_hex"],
    )
    assert verify_pedersen_open(
        opening,
        cm_w_point_hex=mc["point_hex"],
        cm_w_digest_hex=mc["digest_hex"],
        num_weights=setup_artifact["model_commitment"].get("num_weights"),
        setup_json_path=SETUP,
    )
