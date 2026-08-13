"""cp-snark-full prove with trained run_dir (independent of vpin-server-crypto)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_backend.crypto.challenge import sample_challenge
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge
from vpin_backend.protocol.messages import ClientChallenge as BackendChallenge
from vpin_backend.protocol.server_inputs import ProveRequest

STANDARD_RUN = REPO / "model_training" / "outputs" / "20260622_184254"
EC_WITNESS = STANDARD_RUN / "proof_artifacts" / "ec_witness" / "pointMult" / "weight.json"


def _to_backend(ch) -> BackendChallenge:
    return BackendChallenge(
        gamma=ch.gamma,
        gamma_add=ch.gamma_add,
        gamma_mult=ch.gamma_mult,
        num_pt_add=ch.num_pt_add,
        num_pt_mult=ch.num_pt_mult,
    )


@pytest.fixture
def bridge() -> CpSnarkBridge:
    b = CpSnarkBridge(repo_root=REPO)
    if not b.is_available():
        pytest.skip("cp-snark-full missing")
    return b


@pytest.mark.skipif(not EC_WITNESS.is_file(), reason="trained ec_witness missing")
def test_cp_snark_prove_trained_run(bridge: CpSnarkBridge) -> None:
    ch = sample_challenge(num_pt_add=2144, num_pt_mult=178)
    result = bridge.run_prove_with_challenge(
        ProveRequest(
            session_id="test-trained",
            network_id="A",
            model_id="cnn-mnist-trained",
            run_dir=STANDARD_RUN,
            challenge=_to_backend(ch),
        )
    )
    assert result.ok, (result.stderr, result.stdout)
    assert result.artifact_path and result.artifact_path.is_file()
    assert result.summary and result.summary.get("proof_coverage")

    verify = bridge.verify_artifact(result.artifact_path)
    assert verify.ok, verify.stderr
