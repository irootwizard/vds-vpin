"""Official MNIST data loading for vPIN client."""

from __future__ import annotations

from vpin_client.data.core import PreprocessResult, preprocess_uint8_28x28
from vpin_client.data.mnist_loader import fetch_mnist_test_sample


def load_official_test(mnist_index: int) -> PreprocessResult:
    if mnist_index < 0 or mnist_index > 9999:
        raise IndexError(f"MNIST index must be 0..9999, got {mnist_index}")
    image, label = fetch_mnist_test_sample(mnist_index)
    return preprocess_uint8_28x28(
        image,
        label=label,
        index=mnist_index,
        source="official",
    )


def load_official_batch(start: int = 0, count: int = 10) -> list[PreprocessResult]:
    results: list[PreprocessResult] = []
    for i in range(start, min(start + count, 10000)):
        results.append(load_official_test(i))
    return results
