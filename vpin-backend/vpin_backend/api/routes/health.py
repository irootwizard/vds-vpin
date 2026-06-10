from __future__ import annotations

from fastapi import APIRouter

from vpin_backend.config import get_settings
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    bridge = CpSnarkBridge()
    return {
        "status": "ok",
        "repo_root": str(settings.repo_root),
        "bsgs_table_exists": settings.resolved_bsgs_table.is_file(),
        "cp_snark_available": bridge.is_available(),
    }
