"""Batch MNIST AHE evaluation via pipeline.

Single-image submission logic (`run_ahe_inference` / `run_ahe_session`) is unchanged.
This adds a batch layer with two modes:
  - concurrency == 1: serial, identical to the original behavior (fresh keypair/image).
  - concurrency  > 1: P1+P2 pipeline — one shared client keypair across the batch,
    bounded concurrent WebSocket sessions (asyncio); the server offloads homomorphic
    compute to its process pool so sessions run in parallel.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from vpin_client.crypto.ahe.curve import key_gen
from vpin_client.data.input_loader import load_inference_input
from vpin_client.pipeline.ahe_pipeline import run_ahe_inference
from vpin_client.pipeline.types import InferenceJob, ProgressCallback


@dataclass
class BatchReport:
    limit: int
    correct: int
    accuracy: float
    elapsed_s: float
    concurrency: int = 1
    results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "elapsed_s": self.elapsed_s,
            "concurrency": self.concurrency,
            "results": self.results,
        }


async def run_mnist_batch(
    *,
    model_id: str,
    backend_ws: str,
    limit: int,
    on_progress: ProgressCallback | None = None,
    concurrency: int = 1,
) -> BatchReport:
    if concurrency <= 1:
        return await _run_serial(
            model_id=model_id, backend_ws=backend_ws, limit=limit, on_progress=on_progress
        )
    return await _run_concurrent(
        model_id=model_id,
        backend_ws=backend_ws,
        limit=limit,
        on_progress=on_progress,
        concurrency=concurrency,
    )


async def _run_serial(
    *,
    model_id: str,
    backend_ws: str,
    limit: int,
    on_progress: ProgressCallback | None,
) -> BatchReport:
    correct = 0
    results: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    for i in range(limit):
        inp = load_inference_input(mnist_index=i)
        job = InferenceJob(model_id=model_id, backend_ws=backend_ws, mnist_index=i)
        result = await run_ahe_inference(job)
        ok = result.prediction == inp.label
        correct += int(ok)
        results.append({**result.to_dict(), "correct": ok})

        if on_progress:
            elapsed = time.perf_counter() - t0
            eta = elapsed / (i + 1) * (limit - i - 1)
            on_progress(
                "batch_item",
                {
                    "index": i,
                    "limit": limit,
                    "correct": correct,
                    "accuracy": correct / (i + 1),
                    "elapsed_s": elapsed,
                    "eta_s": eta,
                },
            )

    return BatchReport(
        limit=limit,
        correct=correct,
        accuracy=correct / limit if limit else 0.0,
        elapsed_s=time.perf_counter() - t0,
        concurrency=1,
        results=results,
    )


async def _run_concurrent(
    *,
    model_id: str,
    backend_ws: str,
    limit: int,
    on_progress: ProgressCallback | None,
    concurrency: int,
) -> BatchReport:
    shared_keys = key_gen()  # P1: one keypair for the whole batch
    sem = asyncio.Semaphore(concurrency)
    rows: list[dict[str, Any] | None] = [None] * limit
    t0 = time.perf_counter()
    completed = 0
    correct = 0

    async def _one(i: int) -> None:
        nonlocal completed, correct
        async with sem:
            inp = load_inference_input(mnist_index=i)
            job = InferenceJob(model_id=model_id, backend_ws=backend_ws, mnist_index=i)
            result = await run_ahe_inference(job, collect_trace=False, keys=shared_keys)
        ok = result.prediction == inp.label
        rows[i] = {**result.to_dict(), "correct": ok}
        completed += 1
        correct += int(ok)
        if on_progress:
            elapsed = time.perf_counter() - t0
            eta = elapsed / completed * (limit - completed)
            on_progress(
                "batch_item",
                {
                    "index": i,
                    "limit": limit,
                    "correct": correct,
                    "accuracy": correct / completed,
                    "elapsed_s": elapsed,
                    "eta_s": eta,
                },
            )

    await asyncio.gather(*(asyncio.create_task(_one(i)) for i in range(limit)))

    results = [r for r in rows if r is not None]
    return BatchReport(
        limit=limit,
        correct=correct,
        accuracy=correct / limit if limit else 0.0,
        elapsed_s=time.perf_counter() - t0,
        concurrency=concurrency,
        results=results,
    )
