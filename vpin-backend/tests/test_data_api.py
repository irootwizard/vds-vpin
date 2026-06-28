"""Preprocessing is client-only — see vpin_client.data."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from vpin_backend.api.app import create_app

    return TestClient(create_app())


def test_data_preprocess_routes_removed(client) -> None:
    """MNIST/upload preprocess must not run on server (plaintext privacy)."""
    assert client.get("/api/v1/data/official/test/0").status_code == 404
    assert client.get("/api/v1/data/official/batch?start=0&count=3").status_code == 404
    assert client.post("/api/v1/data/upload/preprocess").status_code == 404
