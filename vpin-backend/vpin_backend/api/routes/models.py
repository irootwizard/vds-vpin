from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from vpin_backend.config import get_settings
from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge
from vpin_backend.models.weights_bundle import resolve_weights_dir, store_weights_path
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
        "id": "cnn-mnist-b",
        "name": "CNN Network B (64→32→10)",
        "framework": "npy",
        "task": "图像分类",
        "params_count_m": 2.5,
        "input_shape": "1x28x28",
        "accuracy": 0.0,
        "network": "B",
        "topology": "cnn_mnist_b_v1",
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


def _merged_catalog() -> dict[str, dict]:
    merged = {m["id"]: m for m in _BUILTIN_MODELS}
    for entry in _load_registry():
        merged[entry["id"]] = entry
    return merged


@router.get("/models")
def list_models(capability: str | None = Query(None)) -> list[ModelSummary] | dict:
    merged = _merged_catalog()
    if capability == "ahe":
        from vpin_backend.models.capabilities import list_ahe_capable_models

        return {"models": list_ahe_capable_models(list(merged.values()))}

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


def _weights_dir_for_model(model_id: str) -> Path | None:
    entry = _merged_catalog().get(model_id)
    if not entry:
        return None
    settings = get_settings()
    default = settings.cnn_networks_dir / "Pre_trained_model"
    if entry.get("weights_dir") or entry.get("weight_dir") or entry.get("storage_path"):
        resolved = resolve_weights_dir(entry, default)
        if resolved.is_dir():
            return resolved
    sp = entry.get("storage_path")
    if sp:
        p = Path(sp)
        if not p.is_absolute():
            p = settings.repo_root / p
        npy = p / "npy"
        return npy if npy.is_dir() else p
    return None


@router.get("/models/{model_id}/ahe-manifest")
def get_ahe_manifest(model_id: str) -> dict:
    """Return homomorphic deploy plan + manifest for a registered model."""
    wd = _weights_dir_for_model(model_id)
    if wd is None or not wd.is_dir():
        raise HTTPException(status_code=404, detail="model weights not found")
    plan_path = wd / "homomorphic_deploy_plan.json"
    manifest_path = wd / "ahe_manifest.json"
    if plan_path.is_file():
        return json.loads(plan_path.read_text(encoding="utf-8"))
    if manifest_path.is_file():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    trunc = wd / "truncation_config.json"
    out: dict = {"model_id": model_id, "weights_dir": str(wd)}
    if trunc.is_file():
        out["truncation_config"] = json.loads(trunc.read_text(encoding="utf-8"))
    return out


@router.post("/models/{model_id}/ahe-onboard")
def ahe_onboard(model_id: str) -> dict:
    """Write homomorphic_deploy_plan.json from truncation_config + validation report."""
    import sys

    repo = get_settings().repo_root
    client_root = repo / "vpin-client"
    if str(client_root) not in sys.path:
        sys.path.insert(0, str(client_root))

    wd = _weights_dir_for_model(model_id)
    if wd is None or not wd.is_dir():
        raise HTTPException(status_code=404, detail="model weights not found")

    entry = _merged_catalog().get(model_id, {})
    network = str(entry.get("network", "A")).lower()
    family = "lenet_cifar" if network in ("lenet_cifar", "lenet-cifar") else "network_a"

    from vpin_client.hdc.compile_deploy_plan import compile_deploy_plan, write_deploy_plan
    from vpin_client.hdc.layer_ir import build_lenet_cifar_graph, build_network_a_graph

    graph = build_lenet_cifar_graph() if family == "lenet_cifar" else build_network_a_graph()

    report_path = wd / "hdc_validation_report.json"
    m_pre: dict[str, float] = {}
    accuracy: dict = {}
    accuracy_ok = False
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for pid, chk in report.get("checkpoints", {}).items():
            m_pre[pid] = float(chk.get("M_pre_cal", 0))
        accuracy = report.get("accuracy", {})
        accuracy_ok = bool(report.get("accuracy_ok", accuracy.get("ok", False)))

    plan = compile_deploy_plan(
        model_id=model_id,
        graph=graph,
        m_pre_table=m_pre,
        accuracy=accuracy,
        accuracy_ok=accuracy_ok if report_path.is_file() else None,
    )
    write_deploy_plan(plan, wd / "homomorphic_deploy_plan.json")
    manifest = {
        "model_id": model_id,
        "deployable": plan.deployable,
        "range_ok": plan.range_ok,
        "accuracy_ok": plan.accuracy_ok,
        "adapter_id": plan.adapter_id,
        "family": plan.family,
    }
    (wd / "ahe_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    upsert_model({**entry, "id": model_id, "deployable": plan.deployable, "range_ok": plan.range_ok, "accuracy_ok": plan.accuracy_ok})
    return {"ok": True, "manifest": manifest, "plan_path": str(wd / "homomorphic_deploy_plan.json")}


@router.post("/models", response_model=ModelRegisterResponse)
async def register_model(
    manifest: UploadFile | None = File(None),
    weights: UploadFile | None = File(None),
    npy_bundle: UploadFile | None = File(None),
    model_id: str | None = Form(None),
    name: str | None = Form(None),
    network: str = Form("A"),
) -> ModelRegisterResponse:
    """POST /api/v1/models — register manifest + weights or AHE npy bundle."""
    if not model_id or not name:
        raise HTTPException(status_code=400, detail="form fields model_id and name required")

    req = ModelRegisterRequest(id=model_id, name=name, network=network.upper())
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

    weights_dir: str | None = None
    if npy_bundle:
        from vpin_backend.models.weights_bundle import install_bundle

        bundle_bytes = await npy_bundle.read()
        zip_path = dest / "bundle.zip"
        zip_path.write_bytes(bundle_bytes)
        npy_dest = dest / "npy"
        install_bundle(zip_path, npy_dest, req.network)
        weights_dir = store_weights_path(npy_dest, repo_root=get_settings().repo_root)

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
            "framework": req.framework if not weights_dir else "npy",
            "task": req.task,
            "params_count_m": req.params_count_m,
            "input_shape": req.input_shape or "1x28x28",
            "accuracy": req.accuracy,
            "network": req.network,
            "topology": req.topology or f"cnn_mnist_{req.network.lower()}",
            "updated": now,
            "commitment_digest": commitment_digest,
            "weights_digest_hex": digest_hex,
            "storage_path": str(dest),
            "weights_dir": weights_dir,
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
