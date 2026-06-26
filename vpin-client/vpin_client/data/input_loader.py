"""Load inference input from various sources (MNIST, upload, image file, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vpin_client.data.core import PreprocessResult


def _add_input_digest(result: "PreprocessResult") -> "PreprocessResult":
    """Add input_digest_hex attribute to PreprocessResult."""
    from vpin_client.data.core import compute_input_digest

    digest = compute_input_digest(result.fixed_int32)
    # Add as attribute for backward compatibility
    result.input_digest_hex = digest  # type: ignore[attr-defined]
    return result


def load_inference_input(
    *,
    mnist_index: int | None = None,
    upload_id: str | None = None,
    image_path: Path | str | None = None,
    fixed_npy: Path | str | None = None,
) -> "PreprocessResult":
    """Load and preprocess inference input from various sources.

    Args:
        mnist_index: MNIST test set index (0-9999)
        upload_id: Upload ID for backend-stored data
        image_path: Path to image file
        fixed_npy: Path to pre-quantized .npy file

    Returns:
        PreprocessResult with fixed_int32 ready for AHE encryption
    """
    if mnist_index is not None:
        from vpin_client.data.official import load_official_test

        return _add_input_digest(load_official_test(mnist_index))

    if upload_id:
        # TODO: Implement upload loading via backend API
        raise NotImplementedError(f"upload_id loading not yet implemented: {upload_id}")

    if image_path:
        return _load_from_image_path(Path(image_path))

    if fixed_npy:
        return _load_from_fixed_npy(Path(fixed_npy))

    # Default: MNIST index 0
    from vpin_client.data.official import load_official_test

    return _add_input_digest(load_official_test(0))


def _load_from_image_path(path: Path) -> "PreprocessResult":
    """Load and preprocess an image file.

    Args:
        path: Path to image file (PNG, JPG, etc.)

    Returns:
        PreprocessResult
    """
    from vpin_client.data.core import preprocess_uint8_28x28

    try:
        from PIL import Image
    except ImportError:
        raise ImportError("PIL is required to load image files")

    # Load image
    img = Image.open(path).convert("L")

    # Resize to 28x28 if needed
    if img.size != (28, 28):
        img = img.resize((28, 28), Image.Resampling.LANCZOS)

    # Convert to numpy array
    raw_uint8 = (255 - np.array(img, dtype=np.uint8)).astype(np.uint8)

    result = preprocess_uint8_28x28(
        raw_uint8,
        source="image",
        filename=str(path.name),
    )
    return _add_input_digest(result)


def _load_from_fixed_npy(path: Path) -> "PreprocessResult":
    """Load pre-quantized fixed-point data from .npy file.

    Args:
        path: Path to .npy file with shape (1, 1, 32, 32)

    Returns:
        PreprocessResult
    """
    import numpy as np

    from vpin_client.data.core import PreprocessResult

    fixed = np.load(path)

    if fixed.shape != (1, 1, 32, 32):
        raise ValueError(f"Expected shape (1, 1, 32, 32), got {fixed.shape}")

    result = PreprocessResult(
        raw_uint8=np.zeros((28, 28), dtype=np.uint8),  # Not available
        padded_float=fixed.astype(np.float32) / (2**16),
        normalized_float=fixed.astype(np.float32) / (2**16),
        fixed_int32=fixed.astype(np.int32),
        source="fixed_npy",
        filename=str(path.name),
    )
    return _add_input_digest(result)


# Import numpy at module level for _load_from_image_path
import numpy as np
