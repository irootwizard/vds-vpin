"""Batch AHE evaluation via pipeline.

Single-image submission logic (`run_ahe_inference` / `run_ahe_session`) is unchanged.
Supports arbitrary job lists (MNIST range, indices, uploads) with asyncio concurrency.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vpin_client.crypto.ahe.curve import key_gen
from vpin_client.data.input_loader import load_inference_input
from vpin_client.pipeline.ahe_pipeline import run_ahe_inference
from vpin_client.pipeline.types import InferenceJob, ProgressCallback

TraceMode = Literal["none", "focus", "all"]


def job_id_for(job: InferenceJob) -> str:
    if job.mnist_index is not None:
        return f"mnist-{job.mnist_index}"
    if job.upload_id:
        return f"upload-{job.upload_id[:12]}"
    if job.image_path:
        return f"image-{Path(job.image_path).name}"
    if job.fixed_npy:
        return f"npy-{Path(job.fixed_npy).name}"
    return "job-unknown"


def jobs_from_range(*, model_id: str, backend_ws: str, start: int, limit: int) -> list[InferenceJob]:
    return [
        InferenceJob(model_id=model_id, backend_ws=backend_ws, mnist_index=start + i)
        for i in range(limit)
    ]


def jobs_from_indices(*, model_id: str, backend_ws: str, indices: list[int]) -> list[InferenceJob]:
    return [
        InferenceJob(model_id=model_id, backend_ws=backend_ws, mnist_index=idx) for idx in indices
    ]


def jobs_from_json(raw: list[dict[str, Any]], *, model_id: str, backend_ws: str) -> list[InferenceJob]:
    jobs: list[InferenceJob] = []
    for entry in raw:
        jobs.append(
            InferenceJob(
                model_id=entry.get("model_id") or model_id,
                backend_ws=entry.get("backend_ws") or backend_ws,
                mnist_index=entry.get("mnist_index"),
                upload_id=entry.get("upload_id"),
                image_path=entry.get("image_path"),
                fixed_npy=entry.get("fixed_npy"),
            )
        )
    return jobs


@dataclass
class BatchRequest:
    jobs: list[InferenceJob]
    concurrency: int = 1
    trace_mode: TraceMode = "none"
    engine: str = "python"
    focus_job_id: str | None = None

    @property
    def total(self) -> int:
        return len(self.jobs)


@dataclass
class BatchReport:
    limit: int
    correct: int
    accuracy: float
    elapsed_s: float
    concurrency: int = 1
    start: int | None = None
    engine: str = "python"
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "limit": self.limit,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "elapsed_s": self.elapsed_s,
            "concurrency": self.concurrency,
            "engine": self.engine,
            "results": self.results,
        }
        if self.start is not None:
            out["start"] = self.start
        if self.errors:
            out["errors"] = self.errors
        total_crypto = sum(
            r.get("timing", {}).get("crypto_infer_ms", 0) or 0 for r in self.results
        )
        if self.results:
            out["avg_crypto_infer_ms"] = total_crypto / len(self.results)
        if self.elapsed_s > 0:
            out["img_per_s"] = self.limit / self.elapsed_s
        return out


def _effective_trace_mode(request: BatchRequest) -> TraceMode:
    if request.trace_mode == "all" and request.concurrency > 1:
        return "focus"
    return request.trace_mode


async def run_ahe_batch(
    request: BatchRequest,
    on_progress: ProgressCallback | None = None,
) -> BatchReport:
    total = request.total
    if total == 0:
        return BatchReport(
            limit=0,
            correct=0,
            accuracy=0.0,
            elapsed_s=0.0,
            concurrency=request.concurrency,
            engine=request.engine,
        )

    job_keys = [job_id_for(j) for j in request.jobs]
    if on_progress:
        start_payload: dict[str, Any] = {
            "total": total,
            "concurrency": request.concurrency,
            "engine": request.engine,
            "model_id": request.jobs[0].model_id,
        }
        # 大批量不传 job_keys，避免 NDJSON/UI 卡顿
        if total <= 500:
            start_payload["job_keys"] = job_keys
        on_progress("batch_start", start_payload)

    trace_mode = _effective_trace_mode(request)
    focus_id = request.focus_job_id
    focus_lock = asyncio.Lock()

    async def set_focus(jid: str) -> None:
        nonlocal focus_id
        async with focus_lock:
            if focus_id is None:
                focus_id = jid

    if request.concurrency <= 1:
        report = await _run_serial_jobs(
            request.jobs,
            trace_mode=trace_mode,
            focus_id=focus_id,
            set_focus=set_focus,
            on_progress=on_progress,
            engine=request.engine,
        )
    else:
        report = await _run_concurrent_jobs(
            request.jobs,
            concurrency=request.concurrency,
            trace_mode=trace_mode,
            focus_id=focus_id,
            set_focus=set_focus,
            on_progress=on_progress,
            engine=request.engine,
        )

    if on_progress:
        on_progress("batch_done", {"report": report.to_dict()})
    return report


async def run_mnist_batch(
    *,
    model_id: str,
    backend_ws: str,
    limit: int,
    on_progress: ProgressCallback | None = None,
    concurrency: int = 1,
    start: int = 0,
) -> BatchReport:
    """Legacy wrapper: official MNIST indices [start, start+limit)."""
    request = BatchRequest(
        jobs=jobs_from_range(model_id=model_id, backend_ws=backend_ws, start=start, limit=limit),
        concurrency=concurrency,
    )
    report = await run_ahe_batch(request, on_progress=on_progress)
    report.start = start
    return report


async def _run_serial_jobs(
    jobs: list[InferenceJob],
    *,
    trace_mode: TraceMode,
    focus_id: str | None,
    set_focus,
    on_progress: ProgressCallback | None,
    engine: str,
) -> BatchReport:
    correct = 0
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    total = len(jobs)

    for slot, job in enumerate(jobs):
        jid = job_id_for(job)
        await set_focus(jid)
        if on_progress:
            on_progress(
                "batch_item_start",
                {
                    "slot": slot,
                    "job_id": jid,
                    "mnist_index": job.mnist_index,
                    "upload_id": job.upload_id,
                    "image_path": str(job.image_path) if job.image_path else None,
                },
            )

        collect_trace = trace_mode in ("all", "focus")
        child_cb = _make_item_progress(
            jid, slot, on_progress, emit_trace=collect_trace
        )

        try:
            inp = _load_input(job)
            result = await run_ahe_inference(
                job,
                on_progress=child_cb if collect_trace else None,
                collect_trace=collect_trace,
            )
            label = inp.label
            ok = label is not None and result.prediction == label
            row = {**result.to_dict(), "correct": ok, "job_id": jid}
            results.append(row)
            correct += int(ok)
            if on_progress:
                elapsed = time.perf_counter() - t0
                done = slot + 1
                on_progress(
                    "batch_item_done",
                    {
                        "slot": slot,
                        "job_id": jid,
                        "prediction": result.prediction,
                        "label": label,
                        "correct_item": ok,
                        "correct": correct,
                        "timing": result.to_dict().get("timing"),
                        "elapsed_s": elapsed,
                        "completed": done,
                        "total": total,
                        "accuracy": correct / done,
                        "eta_s": elapsed / done * (total - done) if done else 0,
                    },
                )
                on_progress(
                    "batch_item",
                    {
                        "index": slot,
                        "limit": total,
                        "correct": correct,
                        "accuracy": correct / done,
                        "elapsed_s": elapsed,
                        "eta_s": elapsed / done * (total - done) if done else 0,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            err = {"job_id": jid, "slot": slot, "error": str(exc)}
            errors.append(err)
            if on_progress:
                on_progress("batch_item_done", {**err, "correct": False, "failed": True})

    return BatchReport(
        limit=total,
        correct=correct,
        accuracy=correct / total if total else 0.0,
        elapsed_s=time.perf_counter() - t0,
        concurrency=1,
        engine=engine,
        results=results,
        errors=errors,
    )


async def _run_concurrent_jobs(
    jobs: list[InferenceJob],
    *,
    concurrency: int,
    trace_mode: TraceMode,
    focus_id: str | None,
    set_focus,
    on_progress: ProgressCallback | None,
    engine: str,
) -> BatchReport:
    shared_keys = key_gen()
    sem = asyncio.Semaphore(concurrency)
    rows: list[dict[str, Any] | None] = [None] * len(jobs)
    errors: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    completed = 0
    correct = 0
    total = len(jobs)
    focus_ref: dict[str, str | None] = {"id": focus_id}

    async def _one(slot: int, job: InferenceJob) -> None:
        nonlocal completed, correct
        jid = job_id_for(job)
        await set_focus(jid)
        if focus_ref["id"] is None:
            focus_ref["id"] = jid
        if on_progress:
            on_progress(
                "batch_item_start",
                {
                    "slot": slot,
                    "job_id": jid,
                    "mnist_index": job.mnist_index,
                    "upload_id": job.upload_id,
                    "image_path": str(job.image_path) if job.image_path else None,
                },
            )

        def child_cb(phase: str, data: dict) -> None:
            if phase != "trace" or trace_mode == "none" or not on_progress:
                return
            if trace_mode == "focus" and focus_ref["id"] != jid:
                return
            on_progress("trace", {"job_id": jid, "slot": slot, "step": data})

        try:
            async with sem:
                inp = _load_input(job)
                emit_trace = trace_mode != "none"
                result = await run_ahe_inference(
                    job,
                    on_progress=child_cb if emit_trace else None,
                    collect_trace=emit_trace,
                    keys=shared_keys,
                )
            label = inp.label
            ok = label is not None and result.prediction == label
            rows[slot] = {**result.to_dict(), "correct": ok, "job_id": jid}
        except Exception as exc:  # noqa: BLE001
            errors.append({"job_id": jid, "slot": slot, "error": str(exc)})
            rows[slot] = None

        completed += 1
        if rows[slot] is not None:
            correct += int(rows[slot]["correct"])
        if on_progress:
            elapsed = time.perf_counter() - t0
            payload: dict[str, Any] = {
                "slot": slot,
                "job_id": jid,
                "completed": completed,
                "total": total,
                "correct": correct,
                "accuracy": correct / completed,
                "elapsed_s": elapsed,
                "eta_s": elapsed / completed * (total - completed) if completed else 0,
            }
            if rows[slot]:
                payload.update(
                    {
                        "prediction": rows[slot]["prediction"],
                        "label": rows[slot].get("label"),
                        "correct_item": rows[slot]["correct"],
                        "timing": rows[slot].get("timing"),
                    }
                )
            else:
                payload["failed"] = True
                payload["error"] = errors[-1]["error"] if errors else "unknown"
            on_progress("batch_item_done", payload)
            on_progress(
                "batch_item",
                {
                    "index": slot,
                    "limit": total,
                    "correct": correct,
                    "accuracy": correct / completed,
                    "elapsed_s": elapsed,
                    "eta_s": elapsed / completed * (total - completed) if completed else 0,
                },
            )

    await asyncio.gather(*(asyncio.create_task(_one(i, job)) for i, job in enumerate(jobs)))

    results = [r for r in rows if r is not None]
    return BatchReport(
        limit=total,
        correct=correct,
        accuracy=correct / total if total else 0.0,
        elapsed_s=time.perf_counter() - t0,
        concurrency=concurrency,
        engine=engine,
        results=results,
        errors=errors,
    )


def _load_input(job: InferenceJob):
    if job.mnist_index is not None:
        return load_inference_input(mnist_index=job.mnist_index)
    if job.upload_id:
        return load_inference_input(upload_id=job.upload_id)
    if job.image_path:
        return load_inference_input(image_path=Path(job.image_path))
    if job.fixed_npy:
        return load_inference_input(fixed_npy=Path(job.fixed_npy))
    return load_inference_input(mnist_index=0)


def _make_item_progress(
    jid: str,
    slot: int,
    on_progress: ProgressCallback | None,
    *,
    emit_trace: bool,
) -> ProgressCallback | None:
    if not on_progress:
        return None

    def _cb(phase: str, data: dict) -> None:
        if phase == "trace":
            if emit_trace:
                on_progress("trace", {"job_id": jid, "slot": slot, "step": data})
        else:
            on_progress(phase, {**data, "job_id": jid, "slot": slot})

    return _cb
