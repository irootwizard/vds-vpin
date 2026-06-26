"""Official MNIST data loading for vPIN client."""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass

import numpy as np


@dataclass
class PreprocessResult:
    """Result of image preprocessing."""
    raw_uint8: np.ndarray
    padded_float: np.ndarray
    normalized_float: np.ndarray
    fixed_int32: np.ndarray
    label: int | None = None
    mnist_index: int | None = None
    source: str = "official"
    upload_id: str | None = None
    filename: str | None = None


def _load_mnist_test() -> tuple[np.ndarray, np.ndarray]:
    """Load MNIST test data from torchvision MNIST dataset."""
    try:
        from torchvision import datasets
        from pathlib import Path

        # Download and load MNIST test dataset
        mnist_root = Path("./data/mnist")
        test_dataset = datasets.MNIST(root=mnist_root, train=False, download=True)

        # Convert to numpy arrays
        test_images = test_dataset.data.numpy()  # Shape: (10000, 28, 28)
        test_labels = test_dataset.targets.numpy()  # Shape: (10000,)

        return test_images, test_labels

    except ImportError:
        # Fallback to random data if torchvision not available
        import warnings
        warnings.warn("torchvision not available, using random MNIST data")
        test_images = np.random.randint(0, 256, (10000, 28, 28), dtype=np.uint8)
        test_labels = np.random.randint(0, 10, (10000,), dtype=np.uint8)
        return test_images, test_labels


def _pad_to_32x32(x_f: np.ndarray) -> np.ndarray:
    """Pad 28x28 to 32x32 in 4D format (1,1,32,32)."""
    out = np.zeros((1, 1, 32, 32), dtype=np.float32)
    out[0, 0, 2:30, 2:30] = x_f
    return out


def load_official_test(mnist_index: int) -> PreprocessResult:
    """Load and preprocess a single MNIST test sample.

    Args:
        mnist_index: MNIST test index (0-9999)

    Returns:
        PreprocessResult with preprocessed data
    """
    if mnist_index < 0 or mnist_index > 9999:
        raise IndexError(f"MNIST index must be 0-9999, got {mnist_index}")

    test_images, test_labels = _load_mnist_test()

    if mnist_index >= len(test_images):
        raise IndexError(f"MNIST index {mnist_index} out of range")

    image = test_images[mnist_index]
    label = int(test_labels[mnist_index])

    # Preprocess
    x_f = image.astype(np.float32) / 255.0
    x_padded = _pad_to_32x32(x_f)  # Now returns (1, 1, 32, 32)

    # Convert to fixed point (simplified)
    x_fixed = (x_padded * 2**16).astype(np.int32)  # Will be (1, 1, 32, 32)

    # For normalized_float, store the 28x28 center region from padded array
    x_normalized = x_padded[0, 0, 2:30, 2:30].copy()  # Extract 28x28 center

    return PreprocessResult(
        raw_uint8=image,
        padded_float=x_padded,
        normalized_float=x_normalized,
        fixed_int32=x_fixed,
        label=label,
        mnist_index=mnist_index,
        source="official",
    )


def load_official_batch(start: int = 0, count: int = 10) -> list[PreprocessResult]:
    """Load and preprocess a batch of MNIST test samples.

    Args:
        start: Starting index
        count: Number of samples

    Returns:
        List of PreprocessResult objects
    """
    results = []
    for i in range(start, min(start + count, 10000)):
        try:
            result = load_official_test(i)
            results.append(result)
        except IndexError:
            break
    return results
