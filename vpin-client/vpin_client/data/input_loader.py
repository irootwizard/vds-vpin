"""Load inference input from various sources (MNIST, upload, image file, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vpin_client.data.core import PreprocessResult


def _add_input_digest(result: "PreprocessResult") -> "PreprocessResult":
    """Add input_digest_hex attribute to PreprocessResult."""
    from vpin_client.data.core import compute_input_digest

    digest = compute_input_digest(result.fixed_int32)
    result.input_digest_hex = digest  # type: ignore[attr-defined]
    return result


def load_inference_input(
    *,
    mnist_index: int | None = None,
    upload_id: str | None = None,
    image_path: Path | str | None = None,
    fixed_npy: Path | str | None = None,
) -> "PreprocessResult":
    """Load and preprocess inference input locally (plaintext stays on client).

    Args:
        mnist_index: MNIST test set index (0-9999)
        upload_id: Reserved; use image_path for local uploads
        image_path: Path to image file on client machine
        fixed_npy: Path to pre-quantized .npy file

    Returns:
        PreprocessResult with fixed_int32 ready for AHE encryption
    """
    if mnist_index is not None:
        from vpin_client.data.official import load_official_test

        return _add_input_digest(load_official_test(mnist_index))

    if upload_id:
        raise NotImplementedError(
            f"upload_id is not supported; use image_path for local uploads ({upload_id})"
        )

    if image_path:
        from vpin_client.data.upload import preprocess_upload_path

        return _add_input_digest(preprocess_upload_path(Path(image_path)))

    if fixed_npy:
        return _load_from_fixed_npy(Path(fixed_npy))

    from vpin_client.data.official import load_official_test

    return _add_input_digest(load_official_test(0))


def _load_from_fixed_npy(path: Path) -> "PreprocessResult":
    from vpin_client.data.core import PreprocessResult

    fixed = np.load(path)
    if fixed.shape != (1, 1, 32, 32):
        raise ValueError(f"Expected shape (1, 1, 32, 32), got {fixed.shape}")

    result = PreprocessResult(
        raw_uint8=np.zeros((28, 28), dtype=np.uint8),
        padded_float=fixed.astype(np.float32) / (2**16),
        normalized_float=fixed.astype(np.float32) / (2**16),
        fixed_int32=fixed.astype(np.int32),
        source="fixed_npy",
        filename=str(path.name),
    )
    return _add_input_digest(result)
