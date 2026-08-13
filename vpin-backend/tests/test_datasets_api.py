"""GET /api/v1/datasets/* smoke tests."""

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


def test_datasets_catalog(client) -> None:
    resp = client.get("/api/v1/datasets/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["local"]) >= 1
    assert body["remote"] == []


def test_datasets_remote(client) -> None:
    resp = client.get("/api/v1/datasets/remote")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["items"] == []
