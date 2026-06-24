"""Upload data handling for vPIN backend.

Minimal implementation to fix API errors.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class UploadMeta:
    """Upload metadata."""
    upload_id: str
    filename: str
    source: str = "upload"
    input_digest_hex: str = ""
    preview_png_base64: str = ""


# In-memory storage for uploads (placeholder)
_uploads: dict[str, UploadMeta] = {}


def generate_upload_id() -> str:
    """Generate unique upload ID."""
    import time
    import random
    return f"upload_{int(time.time())}_{random.randint(1000, 9999)}"


def preprocess_and_store_upload(data: bytes, filename: str) -> dict[str, Any]:
    """Preprocess uploaded image and store metadata.

    Args:
        data: Image file data
        filename: Original filename

    Returns:
        Dictionary with preprocessed data
    """
    upload_id = generate_upload_id()

    # Compute digest
    digest = hashlib.sha256(data).hexdigest()

    # Try to create preview
    preview = ""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.mode != 'L':
            img = img.convert('L')
        img = img.resize((28, 28))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        preview = base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception:
        preview = ""

    meta = UploadMeta(
        upload_id=upload_id,
        filename=filename,
        source="upload",
        input_digest_hex=digest,
        preview_png_base64=preview,
    )

    _uploads[upload_id] = meta

    return {
        "source": "upload",
        "upload_id": upload_id,
        "filename": filename,
        "input_digest_hex": digest,
        "preview_png_base64": preview,
        "fixed_shape": [1, 1, 32, 32],
    }


def load_upload_meta(upload_id: str) -> dict[str, Any]:
    """Load upload metadata by ID.

    Args:
        upload_id: Upload ID

    Returns:
        Dictionary with upload metadata

    Raises:
        FileNotFoundError: If upload ID not found
    """
    if upload_id not in _uploads:
        raise FileNotFoundError(f"Upload {upload_id} not found")

    meta = _uploads[upload_id]
    return {
        "source": meta.source,
        "upload_id": meta.upload_id,
        "filename": meta.filename,
        "input_digest_hex": meta.input_digest_hex,
        "preview_png_base64": meta.preview_png_base64,
    }


def list_uploads(limit: int = 50) -> list[dict[str, Any]]:
    """List recent uploads.

    Args:
        limit: Maximum number of uploads to return

    Returns:
        List of upload metadata dictionaries
    """
    uploads = list(_uploads.values())[-limit:]
    return [
        {
            "upload_id": u.upload_id,
            "filename": u.filename,
            "source": u.source,
        }
        for u in reversed(uploads)
    ]
