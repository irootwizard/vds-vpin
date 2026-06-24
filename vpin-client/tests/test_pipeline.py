"""Pipeline layer unit tests (no network)."""

from __future__ import annotations

from vpin_client.pipeline.types import InferenceJob, InferenceResult, InferenceTiming


def test_inference_job_source() -> None:
    assert InferenceJob(model_id="cnn-mnist", mnist_index=0).source() == "official"
    assert InferenceJob(model_id="cnn-mnist", upload_id="u1").source() == "upload"
    assert InferenceJob(model_id="cnn-mnist", image_path="/tmp/x.png").source() == "image"


def test_inference_result_to_dict() -> None:
    r = InferenceResult(
        prediction=3,
        logits=[1.0, 2.0],
        label=3,
        timing=InferenceTiming(preprocess_ms=1.0, crypto_infer_ms=2.0, total_ms=3.0),
    )
    d = r.to_dict()
    assert d["prediction"] == 3
    assert d["timing"]["total_ms"] == 3.0
