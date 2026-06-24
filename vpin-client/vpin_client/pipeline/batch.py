"""Batch MNIST AHE evaluation via pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from vpin_client.data.input_loader import load_inference_input
from vpin_client.pipeline.ahe_pipeline import run_ahe_inference
from vpin_client.pipeline.types import InferenceJob, ProgressCallback


@dataclass
class BatchReport:
    limit: int
    correct: int
    accuracy: float
    elapsed_s: float
    results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "elapsed_s": self.elapsed_s,
            "results": self.results,
        }


async def run_mnist_batch(
    *,
    model_id: str,
    backend_ws: str,
    limit: int,
    on_progress: ProgressCallback | None = None,
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
        row = {**result.to_dict(), "correct": ok}
        results.append(row)

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
        results=results,
    )
