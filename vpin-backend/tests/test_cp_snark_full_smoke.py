"""Smoke tests for cp-snark-full (no vpin-server-crypto setup)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CP_SNARK = REPO / "src" / "cp-snark-full"
STANDARD_RUN = REPO / "model_training" / "outputs" / "20260622_184254"
ARTIFACTS = CP_SNARK / "artifacts" / "A" / "protocol.json"


def _cargo(*args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["VPIN_RUN_DIR"] = str(STANDARD_RUN)
    if env:
        merged.update(env)
    return subprocess.run(
        ["cargo", *args],
        cwd=CP_SNARK,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(not STANDARD_RUN.is_dir(), reason="standard run dir missing")
def test_cp_snark_lib_unit_tests():
    proc = _cargo("test", "--lib", "--", "--quiet")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "test result: ok" in (proc.stdout + proc.stderr)


@pytest.mark.skipif(not STANDARD_RUN.is_dir(), reason="standard run dir missing")
def test_proof_plan_registry_resolves_standard_run():
    backend = REPO / "vpin-backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from vpin_backend.proof.registry import load_proof_plan

    plan = load_proof_plan("A")
    assert plan.run_dir.resolve() == STANDARD_RUN.resolve()
    assert plan.witness.total_pt_mul == 178
    assert plan.witness.total_pt_add == 2144


@pytest.mark.skipif(not ARTIFACTS.is_file(), reason="protocol.json not present; run cargo run -- full A")
def test_verify_saved_protocol_json():
    proc = _cargo("run", "--release", "--", "verify", "A")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "PASSED" in proc.stdout


@pytest.mark.skipif(not ARTIFACTS.is_file(), reason="protocol.json not present")
def test_protocol_has_cps_and_empty_rlc_binding():
    art = json.loads(ARTIFACTS.read_text(encoding="utf-8"))
    assert art.get("cps_commitment") is not None
    assert art.get("rlc_binding_hex", "x") == ""
    assert "layer_proofs_plus_cps" in art.get("proof_coverage", "")
