"""GET /api/v1/health smoke test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))


@pytest.fixture
def client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from vpin_backend.api.app import create_app

    return TestClient(create_app())


def test_health_ok(client) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "server_crypto_available" in body
    assert body.get("cp_snark_deprecated") is True
