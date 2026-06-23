"""HTTPS model upload + catalog cm_W verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class UploadResult:
    ok: bool
    model_id: str
    commitment_digest: str | None = None
    catalog_match: bool = False
    detail: str = ""


def fetch_catalog(base_url: str) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/models"
    with urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_catalog_cm_w(catalog: list[dict[str, Any]], model_id: str, expected_cm_w: str) -> bool:
    for entry in catalog:
        if entry.get("id") == model_id:
            return entry.get("commitment_digest") == expected_cm_w
    return False


def upload_npy_bundle(
    base_url: str,
    *,
    model_id: str,
    name: str,
    bundle_path: Path,
    network: str = "A",
) -> UploadResult:
    """Upload zip npy bundle for AHE inference (sets weights_dir on server)."""
    import mimetypes
    from uuid import uuid4

    if not bundle_path.is_file():
        return UploadResult(ok=False, model_id=model_id, detail=f"missing {bundle_path}")

    boundary = uuid4().hex
    parts: list[bytes] = []

    def add_field(field: str, value: str) -> None:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode()
        )

    add_field("model_id", model_id)
    add_field("name", name)
    add_field("network", network.upper())

    data = bundle_path.read_bytes()
    ctype = mimetypes.guess_type(str(bundle_path))[0] or "application/zip"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="npy_bundle"; filename="{bundle_path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    url = f"{base_url.rstrip('/')}/api/v1/models"
    req = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        return UploadResult(ok=False, model_id=model_id, detail=str(exc))
    return UploadResult(
        ok=bool(payload.get("ok")),
        model_id=model_id,
        commitment_digest=payload.get("commitment_digest"),
        detail=payload.get("storage_path", "upload ok"),
    )


def upload_model(
    base_url: str,
    *,
    model_id: str,
    name: str,
    manifest_path: Path | None = None,
    weights_path: Path | None = None,
    network: str = "A",
) -> UploadResult:
    """Multipart upload to POST /api/v1/models."""
    import mimetypes
    from uuid import uuid4

    boundary = uuid4().hex
    parts: list[bytes] = []

    def add_field(field: str, value: str) -> None:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode()
        )

    add_field("model_id", model_id)
    add_field("name", name)
    add_field("network", network)

    if manifest_path and manifest_path.is_file():
        data = manifest_path.read_bytes()
        ctype = mimetypes.guess_type(str(manifest_path))[0] or "application/json"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="manifest"; filename="{manifest_path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + data
            + b"\r\n"
        )
    if weights_path and weights_path.is_file():
        data = weights_path.read_bytes()
        ctype = mimetypes.guess_type(str(weights_path))[0] or "application/json"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="weights"; filename="{weights_path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + data
            + b"\r\n"
        )

    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    url = f"{base_url.rstrip('/')}/api/v1/models"
    req = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        return UploadResult(ok=False, model_id=model_id, detail=str(exc))

    cm = payload.get("commitment_digest")
    catalog = fetch_catalog(base_url)
    match = verify_catalog_cm_w(catalog, model_id, cm) if cm else False
    return UploadResult(
        ok=bool(payload.get("ok")),
        model_id=model_id,
        commitment_digest=cm,
        catalog_match=match,
        detail="catalog cm_W verified" if match else "upload ok; catalog pin pending",
    )
