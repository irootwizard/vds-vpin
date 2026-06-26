"""Official MNIST data loading for vPIN backend."""

from __future__ import annotations

from typing import Any

from vpin_client.data.core import preprocess_result_to_dict, preprocess_uint8_28x28
from vpin_client.data.mnist_loader import fetch_mnist_test_sample


def preprocess_official_test(index: int) -> dict[str, Any]:
    if index < 0 or index > 9999:
        raise IndexError(f"MNIST index must be 0..9999, got {index}")
    image, label = fetch_mnist_test_sample(index)
    result = preprocess_uint8_28x28(
        image,
        label=label,
        index=index,
        source="official",
    )
    return preprocess_result_to_dict(result)


def preprocess_official_batch(start: int = 0, count: int = 10) -> dict[str, Any]:
    if count < 1 or count > 50:
        raise ValueError(f"count must be 1..50, got {count}")
    if start < 0 or start > 9999:
        raise ValueError(f"start must be 0..9999, got {start}")
    items = []
    for i in range(start, min(start + count, 10000)):
        items.append(preprocess_official_test(i))
    return {"source": "official", "count": len(items), "items": items}
