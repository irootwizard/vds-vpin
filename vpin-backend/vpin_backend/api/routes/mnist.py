"""MNIST dataset index for frontend / API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from vpin_backend.config import get_settings

router = APIRouter(tags=["mnist"])


@router.get("/mnist/index")
def mnist_index() -> dict:
    root = get_settings().resolved_data_dir / "mnist"
    index_path = root / "index.json"
    if not index_path.is_file():
        return {"items": [], "count": 0}
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data
