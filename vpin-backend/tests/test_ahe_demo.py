"""Tests for AHE-capable model listing."""

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

    return TestClient(create_app())


def test_list_ahe_models(client) -> None:
    resp = client.get("/api/v1/models", params={"capability": "ahe"})
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    ids = {m["id"] for m in body["models"]}
    assert "cnn-mnist" in ids
