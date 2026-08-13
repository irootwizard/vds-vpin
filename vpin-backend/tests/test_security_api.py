"""GET /api/v1/security/* smoke tests."""

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


def test_security_transport(client) -> None:
    resp = client.get("/api/v1/security/transport")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tls_enabled"] is False
    assert body["payload_encryption"] == "ahe_ciphertext"
    assert body["certificate"] is None


def test_security_inference_metrics(client) -> None:
    resp = client.get("/api/v1/security/inference-metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_inferences" in body
    assert len(body["usage"]["by_day"]) == 7


def test_security_inference_metrics_record(client) -> None:
    before = client.get("/api/v1/security/inference-metrics").json()
    resp = client.post(
        "/api/v1/security/inference-metrics/record",
        json={"pt_add": 2144, "pt_mult": 178},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    after = client.get("/api/v1/security/inference-metrics").json()
    assert after["total_inferences"] == before["total_inferences"] + 1
    assert after["usage"]["pt_add_total"] == before["usage"]["pt_add_total"] + 2144


def test_security_computation_proof(client) -> None:
    resp = client.get("/api/v1/security/computation-proof")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
