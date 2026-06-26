"""HDC data adapters (§1) — raw sample → encryptable fixed-point tensor.

Registry maps ``adapter_id`` → adapter metadata so the orchestrator (§9) can pick
the right preprocessing per model family without hard-coding datasets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vpin_client.hdc.data_adapters.cifar10_rgb import (
    AdaptedInput,
    adapt_cifar_rgb,
    adapt_cifar_rgb_batch,
)


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    input_shape: tuple[int, ...]
    num_classes: int
    fn: Callable[..., AdaptedInput]
    description: str


_ADAPTERS: dict[str, AdapterSpec] = {
    "cifar_rgb": AdapterSpec(
        adapter_id="cifar_rgb",
        input_shape=(3, 32, 32),
        num_classes=10,
        fn=adapt_cifar_rgb,
        description="CIFAR-10 RGB 3×32×32 per-image min-max, F=16 (LeNet-CIFAR track)",
    ),
}


def get_adapter(adapter_id: str) -> AdapterSpec:
    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:  # noqa: B904
        raise KeyError(f"unknown HDC adapter: {adapter_id}") from exc


def list_adapters() -> list[str]:
    return sorted(_ADAPTERS)


__all__ = [
    "AdaptedInput",
    "AdapterSpec",
    "adapt_cifar_rgb",
    "adapt_cifar_rgb_batch",
    "get_adapter",
    "list_adapters",
]
