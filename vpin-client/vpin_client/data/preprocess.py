"""Re-exports of preprocessing utilities for backward compatibility."""

from vpin_client.data.core import (
    PreprocessResult,
    compute_input_digest,
    preprocess_result_to_dict,
    preprocess_trace_dict,
    preprocess_uint8_28x28,
)
from vpin_client.data.official import load_official_test as load_mnist_test

__all__ = [
    "PreprocessResult",
    "compute_input_digest",
    "load_mnist_test",
    "preprocess_result_to_dict",
    "preprocess_trace_dict",
    "preprocess_uint8_28x28",
]
