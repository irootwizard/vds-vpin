"""WebSocket pure AHE session handshake tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))


@pytest.fixture
def client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from vpin_backend.api.app import create_app

    try:
        return TestClient(create_app())
    except TypeError as exc:
        pytest.skip(f"TestClient unavailable: {exc}")


def test_ws_ahe_handshake(client) -> None:
    """P0–P2: SessionStart → ModelSelectAck → InputDigestAck (no ciphertext)."""
    with client.websocket_connect("/api/v1/session/ws") as ws:
        ws.send_json(
            {"type": "SessionStart", "client_version": "test", "ahe_params_id": "e2-default"}
        )
        accept = ws.receive_json()
        assert accept["type"] == "SessionAccept"
        assert accept.get("session_id")

        ws.send_json({"type": "ModelSelect", "model_id": "cnn-mnist"})
        ack = ws.receive_json()
        assert ack["type"] == "ModelSelectAck"
        assert ack.get("model_id") == "cnn-mnist"
        assert ack.get("network_id") == "A"
        assert ack.get("truncation_plan", {}).get("phases")

        ws.send_json(
            {
                "type": "InputDigest",
                "input_digest_hex": "ab" * 32,
                "shape": [1, 1, 32, 32],
                "fixed_point_bits": 16,
            }
        )
        digest_ack = ws.receive_json()
        assert digest_ack["type"] == "InputDigestAck"
