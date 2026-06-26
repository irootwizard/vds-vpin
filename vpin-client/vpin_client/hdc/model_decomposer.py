"""HDC §7/§8 ModelDecomposer: weights + G_family → LayerGraph G.

``G_family`` registry maps a model family to a graph builder. ``decompose`` returns
the structural ``LayerGraph`` (scales from formula) optionally annotated with
weight magnitude bounds extracted from a quantized weight bundle.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from vpin_client.hdc.layer_ir import (
    LayerGraph,
    build_lenet_cifar_graph,
    build_network_a_graph,
)
from vpin_client.hdc import scale_rules as sr

# G_family → builder. Two families are supported in P2:
#   - network_a    (MNIST 1×28×28, reference track)
#   - lenet_cifar  (CIFAR-10 3×32×32, validation track)
_FAMILIES: dict[str, Callable[..., LayerGraph]] = {
    "network_a": build_network_a_graph,
    "lenet_cifar": build_lenet_cifar_graph,
}

# Hard data ↔ family constraint (§12 session / orchestrator gate).
FAMILY_DATASETS: dict[str, frozenset[str]] = {
    "network_a": frozenset({"mnist"}),
    "network_b": frozenset({"mnist"}),
    "lenet_cifar": frozenset({"cifar10"}),
}

FAMILY_ADAPTERS: dict[str, str] = {
    "network_a": "mnist",
    "lenet_cifar": "cifar_rgb",
}


def list_families() -> list[str]:
    return sorted(_FAMILIES)


def build_layer_graph(family: str, **kwargs: Any) -> LayerGraph:
    try:
        builder = _FAMILIES[family]
    except KeyError as exc:  # noqa: B904
        raise KeyError(f"unknown G_family: {family} (known: {list_families()})") from exc
    return builder(**kwargs)


def family_supports_dataset(family: str, dataset: str) -> bool:
    return dataset.lower() in FAMILY_DATASETS.get(family, frozenset())


def quantize_weight(w: np.ndarray, bits: int = sr.F) -> np.ndarray:
    """Truncate-toward-zero fixed-point quantization (matches real_to_fixed_point)."""
    return (np.asarray(w, dtype=np.float64) * (2**bits)).astype(np.int64)


def decompose(
    family: str,
    weights: dict[str, np.ndarray] | None = None,
    **kwargs: Any,
) -> LayerGraph:
    """Decompose(weights, G_family) → G (§8).

    When ``weights`` are provided (npy bundle keyed by node name, e.g. ``fc1`` →
    weight array), annotate fc nodes with quantized weight/bias max-abs for the
    §6 static bound. Topology and scales are family-defined regardless.
    """
    graph = build_layer_graph(family, **kwargs)
    if not weights:
        return graph
    for node in graph.nodes:
        if node.op != "fc":
            continue
        w = weights.get(f"weight_{node.name}")
        b = weights.get(f"bias_{node.name}")
        if w is not None:
            node.params["max_abs_weight_fp"] = int(np.max(np.abs(quantize_weight(w))))
        if b is not None:
            node.params["max_abs_bias_fp"] = int(np.max(np.abs(quantize_weight(b))))
    return graph
