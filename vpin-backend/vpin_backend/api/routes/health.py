from __future__ import annotations

from fastapi import APIRouter

from vpin_backend.config import get_settings
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge
from vpin_backend.crypto.server_crypto.bridge import ServerCryptoBridge

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    server_crypto = ServerCryptoBridge()
    legacy = CpSnarkBridge()
    return {
        "status": "ok",
        "repo_root": str(settings.repo_root),
        "bsgs_table_exists": settings.resolved_bsgs_table.is_file(),
        "server_crypto_available": server_crypto.is_available(),
        "cp_snark_available": legacy.is_available(),
        "cp_snark_deprecated": True,
        "preferred_crypto_bridge": "server-crypto",
    }
