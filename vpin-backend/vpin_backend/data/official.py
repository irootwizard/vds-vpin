"""Official MNIST data loading for vPIN backend."""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class OfficialSample:
    """Single MNIST test sample."""
    mnist_index: int
    label: int
    input_digest_hex: str
    preview_png_base64: str
    source: str = "official"
    # Additional fields for compatibility
    upload_id: str | None = None
    filename: str | None = None


def _load_mnist_test() -> tuple[np.ndarray, np.ndarray]:
    """Load MNIST test data from torchvision MNIST dataset."""
    try:
        from torchvision import datasets

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


def _compute_digest(image: np.ndarray) -> str:
    """Compute SHA256 digest of image data."""
    return hashlib.sha256(image.tobytes()).hexdigest()


def _create_preview_png(image: np.ndarray) -> str:
    """Create base64-encoded PNG preview."""
    try:
        from PIL import Image
        img = Image.fromarray(image, mode='L')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except ImportError:
        # Fallback: create a simple pattern
        # This won't be a valid PNG but will prevent crash
        return ""


def preprocess_official_test(index: int) -> dict[str, Any]:
    """Load and preprocess a single MNIST test sample.

    Args:
        index: MNIST test index (0-9999)

    Returns:
        Dictionary with preprocessed data
    """
    if index < 0 or index > 9999:
        raise IndexError(f"MNIST index must be 0-9999, got {index}")

    test_images, test_labels = _load_mnist_test()

    if index >= len(test_images):
        raise IndexError(f"MNIST index {index} out of range (max {len(test_images)-1})")

    image = test_images[index]
    label = int(test_labels[index])

    # Create preview PNG
    preview = _create_preview_png(image)

    # Compute digest
    digest = _compute_digest(image)

    return {
        "source": "official",
        "mnist_index": index,
        "label": label,
        "input_digest_hex": digest,
        "preview_png_base64": preview,
        "fixed_shape": [1, 1, 32, 32],  # Network A expects (1,1,32,32)
    }


def preprocess_official_batch(start: int = 0, count: int = 10) -> dict[str, Any]:
    """Load and preprocess a batch of MNIST test samples.

    Args:
        start: Starting index (0-9999)
        count: Number of samples (1-50)

    Returns:
        Dictionary with batch data
    """
    if count < 1 or count > 50:
        raise ValueError(f"Count must be 1-50, got {count}")
    if start < 0 or start > 9999:
        raise ValueError(f"Start must be 0-9999, got {start}")

    items = []
    for i in range(start, min(start + count, 10000)):
        try:
            sample = preprocess_official_test(i)
            items.append(sample)
        except IndexError:
            break

    return {
        "source": "official",
        "count": len(items),
        "items": items,
    }
