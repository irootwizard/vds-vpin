"""WebSocket P4→P5 integration test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

from vpin_client.crypto.challenge import sample_challenge


@pytest.fixture
def client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from vpin_backend.api.app import create_app

    try:
        return TestClient(create_app())
    except TypeError as exc:
        pytest.skip(f"TestClient unavailable: {exc}")


def test_ws_p4_p5_flow(client) -> None:
    with client.websocket_connect("/api/v1/session/ws") as ws:
        ws.send_json({"type": "SessionStart", "client_version": "test", "ahe_params_id": "e2-default"})
        accept = ws.receive_json()
        assert accept["type"] == "SessionAccept"
        assert accept.get("session_id")

        ws.send_json({"type": "ModelSelect", "model_id": "cnn-mnist"})
        mc = ws.receive_json()
        assert mc["type"] == "ModelCommitment"
        assert mc.get("cm_W", {}).get("point_hex")

        ws.send_json(
            {
                "type": "InputCommitment",
                "cm_x": {"point_hex": "00" * 32, "digest_hex": "ab" * 32},
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "InputCommitmentAck"

        ws.send_json({"type": "PublicKey", "h": "deadbeef"})
        trunc = ws.receive_json()
        assert trunc["type"] == "TruncateRequest"

        ws.send_json({"type": "CiphertextChunkAck", "chunk_index": 0})
        inf = ws.receive_json()
        assert inf["type"] == "InferenceComplete"
        assert inf["num_pt_add"] >= 0

        ch = sample_challenge(inf["num_pt_add"], inf["num_pt_mult"])
        ws.send_json(
            {
                "type": "ClientChallenge",
                "gamma": ch.gamma,
                "gamma_add": ch.gamma_add,
                "gamma_mult": ch.gamma_mult,
                "num_pt_add": ch.num_pt_add,
                "num_pt_mult": ch.num_pt_mult,
            }
        )
        proof = ws.receive_json()
        assert proof["type"] == "ProofBundle"
        assert proof.get("proof_coverage")

        ws.send_json(
            {
                "type": "VerificationReport",
                "ok": True,
                "cm_W": mc["cm_W"]["point_hex"],
                "cm_x": "00" * 32,
                "gamma_prefix": ch.gamma[:16],
                "proof_coverage": proof["proof_coverage"],
            }
        )
        final = ws.receive_json()
        assert final["type"] == "VerificationReportAck"
