from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from vpin_backend.config import get_settings
from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge
from vpin_backend.protocol.server_inputs import SetupRequest
from vpin_backend.storage.registry import upsert_model

router = APIRouter(tags=["models"])

_BUILTIN_MODELS = [
    {
        "id": "cnn-mnist",
        "name": "CNN (MNIST 预训练)",
        "framework": "PyTorch",
        "task": "图像分类",
        "params_count_m": 1.21,
        "input_shape": "1x28x28",
        "accuracy": 99.1,
        "network": "A",
        "topology": "cnn_mnist_v1",
    },
    {
        "id": "lenet-mnist",
        "name": "LeNet (MNIST 预训练)",
        "framework": "PyTorch",
        "task": "图像分类",
        "params_count_m": 0.06,
        "input_shape": "1x28x28",
        "accuracy": 98.3,
        "network": "lenet",
        "topology": "lenet_mnist",
    },
]


class ModelSummary(BaseModel):
    id: str
    name: str
    framework: str
    task: str
    params_count_m: float
    input_shape: str
    accuracy: float
    updated: str | None = None
    commitment_digest: str | None = None


class ModelRegisterRequest(BaseModel):
    id: str
    name: str
    network: str = "A"
    framework: str = "exported_json"
    task: str = "图像分类"
    params_count_m: float = 0.0
    input_shape: str = ""
    accuracy: float = 0.0
    topology: str = ""
    weights_path: str | None = None


class ModelRegisterResponse(BaseModel):
    ok: bool
    model: ModelSummary
    storage_path: str
    commitment_digest: str | None = None


def _registry_path() -> Path:
    return get_settings().resolved_data_dir / "models" / "registry.json"


def _load_registry() -> list[dict]:
    path = _registry_path()
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("models", [])
    return data


@router.get("/models", response_model=list[ModelSummary])
def list_models() -> list[ModelSummary]:
    merged = {m["id"]: m for m in _BUILTIN_MODELS}
    for entry in _load_registry():
        merged[entry["id"]] = entry
    out: list[ModelSummary] = []
    for m in merged.values():
        out.append(
            ModelSummary(
                id=m["id"],
                name=m["name"],
                framework=m.get("framework", "npy"),
                task=m.get("task", "图像分类"),
                params_count_m=float(m.get("params_count_m", 0)),
                input_shape=m.get("input_shape", ""),
                accuracy=float(m.get("accuracy", 0)),
                updated=m.get("updated"),
                commitment_digest=m.get("commitment_digest"),
            )
        )
    return out


@router.get("/models/{model_id}", response_model=ModelSummary)
def get_model(model_id: str) -> ModelSummary:
    for item in list_models():
        if item.id == model_id:
            return item
    raise HTTPException(status_code=404, detail="model not found")


@router.post("/models", response_model=ModelRegisterResponse)
async def register_model(
    manifest: UploadFile | None = File(None),
    weights: UploadFile | None = File(None),
    model_id: str | None = Form(None),
    name: str | None = Form(None),
    network: str = Form("A"),
) -> ModelRegisterResponse:
    """POST /api/v1/models — register manifest + weights (task3)."""
    if not model_id or not name:
        raise HTTPException(status_code=400, detail="form fields model_id and name required")

    req = ModelRegisterRequest(id=model_id, name=name, network=network)
    settings = get_settings()
    dest = settings.resolved_data_dir / "models" / "uploads" / req.id
    dest.mkdir(parents=True, exist_ok=True)

    if manifest:
        (dest / "manifest.json").write_bytes(await manifest.read())
    else:
        (dest / "manifest.json").write_text(
            json.dumps({"model_id": req.id, "network": req.network}, indent=2),
            encoding="utf-8",
        )

    weights_path = dest / "model_export.json"
    if weights:
        weights_path.write_bytes(await weights.read())

    commitment_digest: str | None = None
    bridge = ServerCryptoBridge()
    if bridge.is_available() and weights_path.is_file():
        setup = bridge.run_setup(
            SetupRequest(network_id=req.network, weights_path=weights_path)
        )
        if setup.ok and setup.setup_path:
            raw = json.loads(setup.setup_path.read_text(encoding="utf-8"))
            commitment_digest = (
                raw.get("model_commitment", {}).get("cm_weights", {}).get("point_hex")
            )

    digest_hex = ""
    if weights_path.is_file():
        digest_hex = hashlib.sha256(weights_path.read_bytes()).hexdigest()

    now = datetime.now(timezone.utc).isoformat()
    upsert_model(
        {
            "id": req.id,
            "name": req.name,
            "framework": req.framework,
            "task": req.task,
            "params_count_m": req.params_count_m,
            "input_shape": req.input_shape,
            "accuracy": req.accuracy,
            "network": req.network,
            "topology": req.topology,
            "updated": now,
            "commitment_digest": commitment_digest,
            "weights_digest_hex": digest_hex,
            "storage_path": str(dest),
        }
    )

    summary = next((m for m in list_models() if m.id == req.id), None)
    assert summary is not None
    return ModelRegisterResponse(
        ok=True,
        model=summary,
        storage_path=str(dest),
        commitment_digest=commitment_digest,
    )
