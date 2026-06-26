"""Data preprocessing API — official MNIST + upload."""

from __future__ import annotations

import io
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


def test_official_test_sample(client) -> None:
    resp = client.get("/api/v1/data/official/test/0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "official"
    assert body["mnist_index"] == 0
    assert body["label"] is not None
    assert len(body["input_digest_hex"]) == 64
    assert body["preview_png_base64"]


def test_official_batch(client) -> None:
    resp = client.get("/api/v1/data/official/batch?start=0&count=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "official"
    assert body["count"] == 3
    assert len(body["items"]) == 3
    assert body["items"][0]["mnist_index"] == 0


def test_upload_preprocess(client) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (28, 28), color=128).save(buf, format="PNG")
    data = buf.getvalue()

    resp = client.post(
        "/api/v1/data/upload/preprocess",
        files={"file": ("test.png", data, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "upload"
    assert body["upload_id"]
    assert body["filename"] == "test.png"
    assert len(body["input_digest_hex"]) == 64

    meta = client.get(f"/api/v1/data/upload/{body['upload_id']}")
    assert meta.status_code == 200
    assert meta.json()["upload_id"] == body["upload_id"]
