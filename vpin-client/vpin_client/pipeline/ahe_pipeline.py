"""AHE end-to-end inference pipeline (L4 — sole orchestration entry)."""

from __future__ import annotations

import time
from pathlib import Path

from vpin_client.data.input_loader import load_inference_input
from vpin_client.pipeline.types import InferenceJob, InferenceResult, InferenceTiming, ProgressCallback
from vpin_client.protocol.ws_ahe_client import run_ahe_session


def _emit(on_progress: ProgressCallback | None, phase: str, **kwargs: object) -> None:
    if on_progress:
        on_progress(phase, dict(kwargs))


async def run_ahe_inference(
    job: InferenceJob,
    *,
    on_progress: ProgressCallback | None = None,
    collect_trace: bool = True,
    keys: object | None = None,
) -> InferenceResult:
    """Load input → WebSocket P0–P3 session → structured result."""
    trace: list[dict] = []

    def _on_trace(step: dict) -> None:
        if collect_trace:
            trace.append(step)
        _emit(on_progress, "trace", **step)

    _emit(on_progress, "preprocess_start", model_id=job.model_id)

    t0 = time.perf_counter()
    if job.mnist_index is not None:
        inp = load_inference_input(mnist_index=job.mnist_index)
    elif job.upload_id:
        inp = load_inference_input(upload_id=job.upload_id)
    elif job.image_path:
        inp = load_inference_input(image_path=Path(job.image_path))
    elif job.fixed_npy:
        inp = load_inference_input(fixed_npy=Path(job.fixed_npy))
    else:
        inp = load_inference_input(mnist_index=0)

    preprocess_ms = (time.perf_counter() - t0) * 1000
    _emit(
        on_progress,
        "preprocess_done",
        digest=inp.input_digest_hex[:16],
        preprocess_ms=preprocess_ms,
    )

    _emit(on_progress, "session_start", backend=job.backend_ws, engine="python")
    session = await run_ahe_session(
        job.backend_ws,
        job.model_id,
        inp.fixed_int32,
        mnist_index=inp.mnist_index,
        label=inp.label,
        preprocess_ms=preprocess_ms,
        on_trace=_on_trace if collect_trace else None,
        keys=keys,
    )
    _emit(
        on_progress,
        "session_done",
        prediction=session.prediction,
        crypto_infer_ms=session.timing.crypto_infer_ms,
    )

    source = job.source()
    return InferenceResult(
        prediction=session.prediction,
        logits=session.logits,
        label=session.label,
        mnist_index=session.mnist_index,
        upload_id=inp.upload_id,
        input_digest_hex=session.input_digest_hex or inp.input_digest_hex,
        model_id=job.model_id,
        num_pt_add=session.num_pt_add,
        num_pt_mult=session.num_pt_mult,
        source=source,
        timing=InferenceTiming(
            preprocess_ms=session.timing.preprocess_ms,
            crypto_infer_ms=session.timing.crypto_infer_ms,
            e2e_post_preprocess_ms=session.timing.e2e_post_preprocess_ms,
            total_ms=session.timing.total_ms,
        ),
        trace=trace,
    )
