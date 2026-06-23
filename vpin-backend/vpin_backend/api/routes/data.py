"""Data preprocessing API — official MNIST (server) vs client upload."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from vpin_backend.data.official import preprocess_official_batch, preprocess_official_test
from vpin_backend.data.upload import list_uploads, load_upload_meta, preprocess_and_store_upload

router = APIRouter(tags=["data"])


@router.get("/data/official/test/{index}")
def official_test_sample(index: int) -> dict:
    if index < 0 or index > 9999:
        raise HTTPException(400, "index must be 0..9999")
    try:
        return preprocess_official_test(index)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/data/official/batch")
def official_test_batch(start: int = 0, count: int = 10) -> dict:
    if count < 1 or count > 50:
        raise HTTPException(400, "count must be 1..50")
    if start < 0 or start > 9999:
        raise HTTPException(400, "start must be 0..9999")
    try:
        return preprocess_official_batch(start, count)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/data/upload/preprocess")
async def upload_preprocess(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(400, "filename required")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        return preprocess_and_store_upload(data, filename=file.filename)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/data/upload/{upload_id}")
def get_upload(upload_id: str) -> dict:
    try:
        return load_upload_meta(upload_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/data/uploads")
def uploads_index(limit: int = 50) -> dict:
    items = list_uploads(limit=min(limit, 100))
    return {"count": len(items), "items": items}
