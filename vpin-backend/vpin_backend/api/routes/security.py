from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from fastapi import APIRouter

from vpin_backend.config import get_settings


class InferenceRecordBody(BaseModel):
    pt_add: int = Field(ge=0)
    pt_mult: int = Field(ge=0)

router = APIRouter(tags=["security"])

_total_inferences = 0
_pt_add_total = 0
_pt_mult_total = 0
_by_day: dict[str, dict[str, int]] = {}


def _ensure_day(d: date) -> dict[str, int]:
    key = d.isoformat()
    if key not in _by_day:
        _by_day[key] = {"inferences": 0, "pt_add": 0, "pt_mult": 0}
    return _by_day[key]


def record_inference_session(pt_add: int, pt_mult: int) -> None:
    """Hook for session completion — increments global counters."""
    global _total_inferences, _pt_add_total, _pt_mult_total
    _total_inferences += 1
    _pt_add_total += pt_add
    _pt_mult_total += pt_mult
    bucket = _ensure_day(date.today())
    bucket["inferences"] += 1
    bucket["pt_add"] += pt_add
    bucket["pt_mult"] += pt_mult


@router.get("/security/transport")
def security_transport() -> dict:
    settings = get_settings()
    api_base = f"http://{settings.api_host}:{settings.api_port}/api/v1"
    ws_host = settings.api_host if settings.api_host != "0.0.0.0" else "127.0.0.1"
    return {
        "tls_enabled": False,
        "http_scheme": "http",
        "ws_scheme": "ws",
        "api_base": api_base,
        "session_ws": f"ws://{ws_host}:{settings.api_port}/api/v1/session/ws",
        "certificate": None,
        "forward_secrecy": False,
        "payload_encryption": "ahe_ciphertext",
    }


@router.post("/security/inference-metrics/record")
def record_inference_metrics(body: InferenceRecordBody) -> dict:
    record_inference_session(body.pt_add, body.pt_mult)
    return {"ok": True}


@router.get("/security/inference-metrics")
def inference_metrics() -> dict:
    today = date.today()
    by_day = []
    delta_7d = 0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        bucket = _by_day.get(d.isoformat(), {"inferences": 0, "pt_add": 0, "pt_mult": 0})
        delta_7d += bucket["inferences"]
        by_day.append(
            {
                "date": d.isoformat(),
                "pt_add": bucket["pt_add"],
                "pt_mult": bucket["pt_mult"],
                "inferences": bucket["inferences"],
            }
        )

    return {
        "total_inferences": _total_inferences,
        "delta_7d": delta_7d,
        "delta_1d": by_day[-1]["inferences"] if by_day else 0,
        "usage": {
            "pt_add_total": _pt_add_total,
            "pt_mult_total": _pt_mult_total,
            "by_day": by_day,
        },
        "proof_overhead": {
            "prove_ms_avg": 0,
            "verify_ms_avg": 0,
            "overhead_ratio": 0.0,
            "by_day": [
                {"date": row["date"], "prove_ms": 0, "verify_ms": 0} for row in by_day
            ],
        },
    }


@router.get("/security/computation-proof")
def computation_proof() -> dict:
    return {
        "status": "pending",
        "last_verified_at": None,
        "coverage": None,
        "message": "计算量证明校验待接入",
    }
