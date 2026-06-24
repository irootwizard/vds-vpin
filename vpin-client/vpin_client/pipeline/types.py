"""Application-layer types for inference pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

ProgressCallback = Callable[[str, dict[str, Any]], None]

InputSource = Literal["official", "upload", "image", "fixed_npy"]


@dataclass
class InferenceJob:
    """Single AHE inference request (L4 application input)."""

    model_id: str
    backend_ws: str = "ws://127.0.0.1:8000/api/v1/session/ws"
    mnist_index: int | None = None
    upload_id: str | None = None
    image_path: Path | str | None = None
    fixed_npy: Path | str | None = None

    def source(self) -> InputSource:
        if self.mnist_index is not None:
            return "official"
        if self.upload_id:
            return "upload"
        if self.image_path:
            return "image"
        if self.fixed_npy:
            return "fixed_npy"
        return "official"


@dataclass
class InferenceTiming:
    preprocess_ms: float = 0.0
    crypto_infer_ms: float = 0.0
    e2e_post_preprocess_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class InferenceResult:
    prediction: int
    logits: list[float]
    label: int | None = None
    mnist_index: int | None = None
    upload_id: str | None = None
    input_digest_hex: str = ""
    model_id: str = ""
    num_pt_add: int = 0
    num_pt_mult: int = 0
    timing: InferenceTiming = field(default_factory=InferenceTiming)
    source: InputSource = "official"

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction": self.prediction,
            "logits": self.logits,
            "label": self.label,
            "mnist_index": self.mnist_index,
            "upload_id": self.upload_id,
            "input_digest_hex": self.input_digest_hex,
            "model_id": self.model_id,
            "num_pt_add": self.num_pt_add,
            "num_pt_mult": self.num_pt_mult,
            "source": self.source,
            "timing": {
                "preprocess_ms": self.timing.preprocess_ms,
                "crypto_infer_ms": self.timing.crypto_infer_ms,
                "e2e_post_preprocess_ms": self.timing.e2e_post_preprocess_ms,
                "total_ms": self.timing.total_ms,
            },
        }
