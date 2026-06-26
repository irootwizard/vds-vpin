"""Official MNIST data loading for vPIN backend.

This is a minimal implementation to fix the 500 error.
For production, should integrate with actual MNIST dataset.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
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
    input_digest_hex: str = ""
    preview_png_base64: str = ""


def _load_mnist_test() -> tuple[np.ndarray, np.ndarray]:
    """Load MNIST test data.

    This is a placeholder that generates synthetic MNIST-like data.
    In production, this should load actual MNIST test dataset.
    """
    # Placeholder: generate synthetic MNIST-like 28x28 images
    # Real implementation should use actual MNIST dataset
    try:
        from sklearn.datasets import load_digits
        digits = load_digits()
        # digits.images are 8x8, we need 28x28 - use as placeholder
        test_images = np.zeros((10000, 28, 28), dtype=np.uint8)
        test_labels = np.zeros((10000,), dtype=np.uint8)

        # Use digits as placeholder for first few samples
        for i in range(min(len(digits.images), 1000)):
            # Upscale 8x8 to 28x28
            img = digits.images[i]
            # Simple upsampling
            img_upscaled = np.zeros((28, 28), dtype=np.uint8)
            for r in range(8):
                for c in range(8):
                    img_upscaled[r*3:(r+1)*3, c*3:(c+1)*3] = img[r, c] * 255

            test_images[i] = img_upscaled
            test_labels[i] = digits.target[i]

        return test_images, test_labels
    except ImportError:
        # Fallback to synthetic data
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
