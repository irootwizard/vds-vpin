"""R4 end-to-end: client γ → server prove → client M1 scalar verify."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-client"))
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_client.crypto.challenge import challenge_from_hex, sample_challenge
from vpin_client.protocol.messages import ProofBundle
from vpin_client.verify.pipeline import ModelOpening, TraceBundle, verify_session
from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge
from vpin_backend.protocol.messages import ClientChallenge as BackendChallenge
from vpin_backend.protocol.server_inputs import ProveRequest, SetupRequest


def _to_backend_challenge(ch) -> BackendChallenge:
    return BackendChallenge(
        gamma=ch.gamma,
        gamma_add=ch.gamma_add,
        gamma_mult=ch.gamma_mult,
        num_pt_add=ch.num_pt_add,
        num_pt_mult=ch.num_pt_mult,
    )


@pytest.fixture
def bridge() -> ServerCryptoBridge:
    b = ServerCryptoBridge(repo_root=REPO)
    if not b.is_available():
        pytest.skip("vpin-server-crypto workspace missing")
    return b


def test_r4_setup_and_prove(bridge: ServerCryptoBridge) -> None:
    net = "A"
    setup = bridge.run_setup(SetupRequest(network_id=net))
    assert setup.ok, setup.stderr

    ch = sample_challenge(num_pt_add=2144, num_pt_mult=178)
    prove = bridge.run_prove_with_challenge(
        ProveRequest(
            session_id="test",
            network_id=net,
            challenge=_to_backend_challenge(ch),
            setup_artifact=setup.setup_path,
        )
    )
    assert prove.ok, prove.stderr
    assert prove.artifact_path and prove.artifact_path.is_file()

    raw = json.loads(prove.artifact_path.read_text(encoding="utf-8"))
    assert raw.get("proof_coverage")


@pytest.mark.skipif(
    not (REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "conv_trace.json").is_file(),
    reason="conv_trace missing",
)
def test_client_m1_scalar_after_prove(bridge: ServerCryptoBridge) -> None:
    net = "A"
    conv_path = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "conv_trace.json"
    pool_path = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "pool_trace.json"

    setup = bridge.run_setup(SetupRequest(network_id=net))
    assert setup.ok

    ch = challenge_from_hex(
        "02" + "00" * 31,
        "03" + "00" * 31,
        "05" + "00" * 31,
        num_pt_add=2144,
        num_pt_mult=178,
    )
    prove = bridge.run_prove_with_challenge(
        ProveRequest(
            session_id="test",
            network_id=net,
            challenge=_to_backend_challenge(ch),
            setup_artifact=setup.setup_path,
        )
    )
    assert prove.ok

    artifact = json.loads(prove.artifact_path.read_text(encoding="utf-8"))
    opening_raw = artifact.get("model_opening") or {}
    opening = ModelOpening(
        weights=[int(w) for w in opening_raw.get("weights", ["1", "2", "3"])],
        blind=opening_raw.get("blind_hex", "00"),
    )
    traces = TraceBundle(
        conv_traces=[json.loads(conv_path.read_text(encoding="utf-8"))],
        pool_traces=[json.loads(pool_path.read_text(encoding="utf-8"))]
        if pool_path.is_file()
        else [],
    )
    bundle = ProofBundle(
        proof_coverage=str(artifact.get("proof_coverage", "skeleton_ec_stub")),
        prove_time_ms=int(artifact.get("prove_time_ms", 0)),
    )
    mc = artifact.get("model_commitment", {})
    cm = mc.get("cm_weights", {})
    report = verify_session(
        bundle,
        opening,
        ch,
        traces,
        skip_fc=True,
        cm_w_point_hex=str(cm.get("point_hex", "")),
        cm_w_digest_hex=str(cm.get("digest_hex", "")),
        num_weights=mc.get("num_weights"),
    )
    assert report.scalar_ok, report.detail
    assert report.opening_ok, "Pedersen opening should verify against protocol artifact"
