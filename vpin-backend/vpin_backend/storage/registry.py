"""Model registry (file-backed MVP for Task3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vpin_backend.config import get_settings


def registry_path() -> Path:
    return get_settings().resolved_data_dir / "models" / "registry.json"


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"models": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def upsert_model(entry: dict[str, Any]) -> None:
    reg = load_registry()
    models: list[dict[str, Any]] = reg.setdefault("models", [])
    model_id = entry.get("id")
    models[:] = [m for m in models if m.get("id") != model_id]
    models.append(entry)
    save_registry(reg)


def get_model(model_id: str) -> dict[str, Any] | None:
    for m in load_registry().get("models", []):
        if m.get("id") == model_id:
            return m
    return None
