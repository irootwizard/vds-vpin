"""Model capability checks (AHE weights availability)."""

from __future__ import annotations

from pathlib import Path

from vpin_backend.config import get_settings
from vpin_backend.models.weights_bundle import resolve_weights_dir
from vpin_backend.storage.registry import get_model

AHE_NETWORKS = frozenset({"A", "B", "lenet_mnist", "lenet_cifar", "lenet_cifar10", "lenet", "resnet18_cifar"})
_BUILTIN_NETWORK = {"cnn-mnist": "A", "cnn-mnist-b": "B"}

_LENET_NETWORKS = frozenset({"lenet_mnist", "lenet_cifar", "lenet_cifar10", "lenet"})
_RESNET_NETWORKS = frozenset({"resnet18_cifar", "resnet18", "resnet18_cifar10"})


def _is_lenet(network: str) -> bool:
    return network.lower().replace("-", "_") in _LENET_NETWORKS


def _is_resnet(network: str) -> bool:
    return network.lower().replace("-", "_") in _RESNET_NETWORKS


def resolve_model_network(model_id: str, entry: dict | None = None) -> str | None:
    entry = entry or get_model(model_id) or {}
    network = entry.get("network") or _BUILTIN_NETWORK.get(model_id)
    if network in AHE_NETWORKS:
        return str(network)
    return None


def model_has_ahe_weights(model_id: str) -> bool:
    entry = get_model(model_id)
    settings = get_settings()
    default = settings.cnn_networks_dir / "Pre_trained_model"
    network = resolve_model_network(model_id, entry)
    if network is None:
        return False

    if model_id == "cnn-mnist":
        weights_dir = default
    elif entry:
        weights_dir = resolve_weights_dir(entry, default)
    else:
        return False

    # LeNet models use truncation_config.json as the deployment-ready marker.
    if _is_lenet(network):
        return (weights_dir / "truncation_config.json").is_file()

    # ResNet models: check all 42 .npy weight files exist.
    if _is_resnet(network):
        from vpin_client.models.resnet_weights_layout import get_resnet_layout

        layout = get_resnet_layout()
        return all((weights_dir / name).is_file() for name in layout.required_files)

    from vpin_client.models.weights_layout import get_layout

    try:
        layout = get_layout(network)
    except KeyError:
        return False
    return all((weights_dir / name).is_file() for name in layout.required_files)


def list_ahe_capable_models(merged_catalog: list[dict]) -> list[dict]:
    items: list[dict] = []
    for m in merged_catalog:
        model_id = m["id"]
        network = resolve_model_network(model_id, m)
        if network is None or not model_has_ahe_weights(model_id):
            continue
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
