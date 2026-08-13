"""Official CIFAR-10 loading + UI preview dict."""

from __future__ import annotations

import base64
import io

import numpy as np

from vpin_client.data.cifar10_loader import fetch_cifar10_sample
from vpin_client.hdc.data_adapters.cifar10_rgb import adapt_cifar_rgb


def _preview_png_base64(chw_uint8: np.ndarray) -> str:
    try:
        from PIL import Image
    except ImportError:
        return ""
    hwc = np.transpose(chw_uint8, (1, 2, 0))
    buf = io.BytesIO()
    Image.fromarray(hwc, mode="RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def load_cifar10_test(index: int, *, train: bool = False) -> dict:
    from vpin_client.data.cifar10_loader import ensure_cifar10_binary_batches

    ensure_cifar10_binary_batches()
    raw, label = fetch_cifar10_sample(index, train=train)
    adapted = adapt_cifar_rgb(raw, label=label, index=index)
    split = "train" if train else "test"
    return {
        "source": f"cifar10-{split}",
        "dataset_id": f"cifar10-{'train' if train else 'test'}",
        "sample_index": index,
        "cifar_index": index,
        "label": label,
        "input_digest_hex": adapted.digest_hex,
        "preview_png_base64": _preview_png_base64(adapted.raw_uint8),
        "fixed_shape": list(adapted.fixed_int32.shape),
        "preview_kind": "rgb",
    }


def load_cifar10_batch(start: int, count: int, *, train: bool = False) -> list[dict]:
    limit = 50_000 if train else 10_000
    end = min(start + count, limit)
    return [load_cifar10_test(i, train=train) for i in range(start, end)]
