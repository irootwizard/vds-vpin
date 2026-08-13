"""Model capability checks (AHE weights availability)."""

from __future__ import annotations

from pathlib import Path

from vpin_backend.config import get_settings
from vpin_backend.models.weights_bundle import resolve_weights_dir
from vpin_backend.storage.registry import get_model
from vpin_client.models.weights_layout import get_layout, is_lenet_cifar

AHE_NETWORKS = frozenset({"A", "B"})
_BUILTIN_NETWORK = {"cnn-mnist": "A", "cnn-mnist-b": "B"}


def resolve_model_network(model_id: str, entry: dict | None = None) -> str | None:
    entry = entry or get_model(model_id) or {}
    network = entry.get("network") or _BUILTIN_NETWORK.get(model_id)
    if network in AHE_NETWORKS:
        return str(network)
    if network and is_lenet_cifar(str(network)):
        return str(network)
    return None


def _weights_dir_for_entry(model_id: str, entry: dict) -> Path | None:
    settings = get_settings()
    default = settings.cnn_networks_dir / "Pre_trained_model"
    if model_id == "cnn-mnist":
        return default
    if entry.get("weights_dir") or entry.get("weight_dir") or entry.get("storage_path"):
        resolved = resolve_weights_dir(entry, default)
        if resolved.is_dir():
            return resolved
    return None


def model_has_ahe_weights(model_id: str) -> bool:
    entry = get_model(model_id) or {}
    network = entry.get("network") or _BUILTIN_NETWORK.get(model_id, "")
    weights_dir = _weights_dir_for_entry(model_id, entry)
    if weights_dir is None:
        return False

    if network in AHE_NETWORKS or model_id == "cnn-mnist":
        net_key = str(network) if network in AHE_NETWORKS else "A"
        try:
            layout = get_layout(net_key)
        except KeyError:
            return False
        return all((weights_dir / name).is_file() for name in layout.required_files)

    if is_lenet_cifar(str(network)):
        from vpin_client.models.lenet_weights_layout import get_lenet_layout

        layout = get_lenet_layout()
        if layout is None:
            return False
        return all((weights_dir / name).is_file() for name in layout.required_files)

    return False


def list_ahe_capable_models(merged_catalog: list[dict]) -> list[dict]:
    items: list[dict] = []
    for m in merged_catalog:
        model_id = m["id"]
        if not model_has_ahe_weights(model_id):
            continue
        network = m.get("network") or _BUILTIN_NETWORK.get(model_id, "")
        items.append(
            {
                "id": model_id,
                "name": m.get("name", model_id),
                "network": network,
                "accuracy": float(m.get("accuracy", 0)),
                "input_shape": m.get("input_shape", ""),
                "framework": m.get("framework", "npy"),
            }
        )
    return items
