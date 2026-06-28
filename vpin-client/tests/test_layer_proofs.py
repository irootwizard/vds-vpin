"""Client layer proof stub verify (M5 partial)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from vpin_client.verify.layer import layer_bundle_from_dict, verify_layer_proofs

REPO = Path(__file__).resolve().parents[2]
LAYER_JSON = REPO / "src" / "cp-snark-full" / "artifacts" / "A" / "layer_proofs.json"


@pytest.fixture(scope="module")
def layer_artifact() -> dict:
    manifest = REPO / "src" / "cp-snark-full" / "Cargo.toml"
    if not manifest.is_file():
        pytest.skip("cp-snark-full missing")
    if not LAYER_JSON.is_file():
        proc = subprocess.run(
            [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                str(manifest),
                "--",
                "prove-layer",
                "A",
            ],
            cwd=str(REPO / "src" / "cp-snark-full"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode != 0:
            pytest.skip(proc.stderr)
    return json.loads(LAYER_JSON.read_text(encoding="utf-8"))


def test_verify_layer_stubs(layer_artifact: dict) -> None:
    bundle = layer_bundle_from_dict(
        {
            "pi_conv": layer_artifact.get("pi_conv_hex"),
            "pi_pool": layer_artifact.get("pi_pool_hex"),
            "pi_fc": layer_artifact.get("pi_fc_hex") or [],
        }
    )
    report = verify_layer_proofs(bundle)
    assert report.ok
    assert report.proof_coverage == "layer_proofs_partial"
