#!/usr/bin/env python3
"""Download official MNIST test set and export visualization artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "vpin-client"))

from vpin_client.data.preprocess import (
    export_preview_png,
    mnist_data_root,
    preprocess_mnist_uint8,
    preview_png_base64,
)

try:
    from torchvision import datasets
except ImportError as exc:
    raise SystemExit("torchvision required: pip install torchvision") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-preview", type=int, default=16, help="export N sample PNGs")
    parser.add_argument("--with-train", action="store_true")
    args = parser.parse_args()

    root = mnist_data_root()
    root.mkdir(parents=True, exist_ok=True)
    test_ds = datasets.MNIST(root=str(root / "raw"), train=False, download=True)
    images = test_ds.data.numpy()
    labels = test_ds.targets.numpy()

    np.save(root / "test_images_uint8.npy", images)
    np.save(root / "test_labels.npy", labels)

    index = [{"index": i, "label": int(labels[i])} for i in range(len(labels))]
    (root / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    manifest = {
        "source": "torchvision.datasets.MNIST",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "test_count": int(len(labels)),
        "shape": [28, 28],
        "dtype": "uint8",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    samples = root / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    n = min(args.export_preview, len(labels))
    for i in range(n):
        prep = preprocess_mnist_uint8(images[i])
        export_preview_png(prep, samples / f"raw_{i:05d}_label_{int(labels[i])}.png", stage="raw")
        export_preview_png(prep, samples / f"padded_{i:05d}_label_{int(labels[i])}.png", stage="padded")

    print(f"MNIST test set: {len(labels)} images -> {root}")


if __name__ == "__main__":
    main()
