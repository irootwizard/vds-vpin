#!/usr/bin/env python
"""Download / probe common MNIST-family formats and compare vPIN preprocessing.

Writes JSON report to reports/dataset_format_analysis.json
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-client"))

from vpin_client.data.core import (  # noqa: E402
    compute_input_digest,
    preprocess_uint8_28x28,
)
from vpin_client.data.mnist_loader import _mnist_test_dataset  # noqa: E402
from vpin_client.data.official import load_official_test  # noqa: E402


def _mnist_raw_dir() -> Path:
    """Official IDX cache: model_training/data/MNIST/raw/."""
    _mnist_test_dataset()  # ensure torchvision download
    return REPO / "model_training" / "data" / "MNIST" / "raw"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _array_stats(arr: np.ndarray) -> dict:
    return {
        "dtype": str(arr.dtype),
        "shape": list(arr.shape),
        "min": int(np.min(arr)) if arr.size else None,
        "max": int(np.max(arr)) if arr.size else None,
        "mean": float(np.mean(arr)) if arr.size else None,
    }


def analyze_official_idx(index: int = 0) -> dict:
    raw_dir = _mnist_raw_dir()
    files = {}
    for fname in (
        "train-images-idx3-ubyte",
        "train-labels-idx1-ubyte",
        "t10k-images-idx3-ubyte",
        "t10k-labels-idx1-ubyte",
    ):
        extracted = raw_dir / fname
        files[fname] = {
            "path": str(extracted),
            "size_bytes": extracted.stat().st_size if extracted.is_file() else 0,
        }
    # Parse IDX header for test images
    img_path = raw_dir / "t10k-images-idx3-ubyte"
    with img_path.open("rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        pixel_bytes = f.read(rows * cols)
    raw_idx = np.frombuffer(pixel_bytes, dtype=np.uint8).reshape(rows, cols)
    prep_official = load_official_test(index)
    return {
        "source": "official_idx",
        "index": index,
        "idx_header": {"magic": magic, "count": n, "rows": rows, "cols": cols},
        "files": files,
        "raw_uint8_stats": _array_stats(raw_idx),
        "vpin": {
            "label": prep_official.label,
            "fixed_shape": list(prep_official.fixed_int32.shape),
            "input_digest_hex": compute_input_digest(prep_official.fixed_int32),
            "fixed_min": int(prep_official.fixed_int32.min()),
            "fixed_max": int(prep_official.fixed_int32.max()),
        },
    }


def _hf_row_via_api(index: int) -> dict:
    import urllib.request

    url = (
        "https://datasets-server.huggingface.co/rows"
        f"?dataset=ylecun/mnist&config=mnist&split=test&offset={index}&length=1"
    )
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["rows"][0]["row"]


def analyze_hf_mnist(index: int = 0) -> dict:
    from PIL import Image

    method = "hf_datasets_server_api"
    try:
        row = _hf_row_via_api(index)
    except Exception as api_exc:
        return {
            "source": "huggingface_ylecun_mnist",
            "hub_id": "ylecun/mnist",
            "error": str(api_exc),
        }

    if isinstance(row["image"], dict) and "src" in row["image"]:
        import urllib.request

        with urllib.request.urlopen(row["image"]["src"], timeout=60) as resp:
            img_bytes = resp.read()
        pil_img = Image.open(BytesIO(img_bytes))
    else:
        pil_img = row["image"]
    raw = np.array(pil_img.convert("L"), dtype=np.uint8)
    prep = preprocess_uint8_28x28(raw, label=int(row["label"]), index=index, source="hf")
    official = load_official_test(index)
    digest_match = compute_input_digest(prep.fixed_int32) == compute_input_digest(
        official.fixed_int32
    )
    raw_match = np.array_equal(raw, official.raw_uint8)
    return {
        "source": "huggingface_ylecun_mnist",
        "hub_id": "ylecun/mnist",
        "load_method": method,
        "split": "test",
        "index": index,
        "features": {
            "image": "PIL.Image 28x28 L",
            "label": "ClassLabel 0-9",
            "storage": "Parquet shards on Hub (auto-converted from IDX)",
        },
        "raw_uint8_stats": _array_stats(raw),
        "vpin_digest_hex": compute_input_digest(prep.fixed_int32),
        "official_digest_hex": compute_input_digest(official.fixed_int32),
        "raw_bytes_match_official": bool(raw_match),
        "vpin_digest_match_official": bool(digest_match),
    }


def analyze_kaggle_csv_style(index: int = 0) -> dict:
    """Synthesize Kaggle digit-recognizer CSV row from official MNIST (same pixel layout)."""
    prep = load_official_test(index)
    raw = prep.raw_uint8
    flat = raw.reshape(-1)
    columns = ["label"] + [f"pixel{i}" for i in range(784)]
    # build one-row CSV in memory
    import csv
    from io import StringIO

    text = StringIO()
    writer = csv.writer(text)
    writer.writerow(columns)
    writer.writerow([prep.label, *flat.tolist()])
    csv_text = text.getvalue()

    text2 = StringIO(csv_text)
    reader = csv.DictReader(text2)
    row = next(reader)
    pixels = np.array([int(row[f"pixel{i}"]) for i in range(784)], dtype=np.uint8).reshape(28, 28)
    prep_csv = preprocess_uint8_28x28(pixels, label=int(row["label"]), source="kaggle_csv")
    return {
        "source": "kaggle_digit_recognizer_csv",
        "description": "train.csv: label + pixel0..pixel783, row-major 28x28, 0-255",
        "csv_header_columns": len(columns),
        "csv_sample_chars": len(csv_text),
        "pixel_index_formula": "pixel_x at row i col j where x = i*28 + j",
        "raw_match_official": bool(np.array_equal(pixels, raw)),
        "vpin_digest_hex": compute_input_digest(prep_csv.fixed_int32),
        "official_digest_hex": compute_input_digest(prep.fixed_int32),
        "digest_match": compute_input_digest(prep_csv.fixed_int32)
        == compute_input_digest(prep.fixed_int32),
    }


def analyze_png_upload(index: int = 0) -> dict:
    from PIL import Image

    prep = load_official_test(index)
    buf = BytesIO()
    Image.fromarray(prep.raw_uint8, mode="L").save(buf, format="PNG")
    png_bytes = buf.getvalue()
    from vpin_client.data.upload import preprocess_upload_bytes

    up = preprocess_upload_bytes(png_bytes, filename="sample.png")
    return {
        "source": "png_upload",
        "png_bytes": len(png_bytes),
        "decode_path": "PIL → L → resize(28,28) LANCZOS",
        "vpin_digest_hex": compute_input_digest(up.fixed_int32),
        "official_digest_hex": compute_input_digest(prep.fixed_int32),
        "digest_match": compute_input_digest(up.fixed_int32)
        == compute_input_digest(prep.fixed_int32),
    }


def analyze_model_npy_bundle() -> dict:
    from vpin_client.models.format_adapter import detect_format, validate_npy_bundle
    from vpin_client.models.weights_layout import LAYOUTS

    candidates: list[Path] = []
    for pattern in (
        "model_training/outputs/*/weight_fc1_*.npy",
        "src/cnn_networks/Pre_trained_model/*.npy",
    ):
        candidates.extend(REPO.glob(pattern))
    dirs: dict[str, Path] = {}
    for p in candidates:
        dirs[str(p.parent)] = p.parent

    bundles = []
    for d in sorted(dirs.values(), key=lambda x: str(x)):
        probe = detect_format(d)
        if probe.format.value != "ahe_npy_bundle":
            continue
        net = probe.network or "?"
        ok, errs = validate_npy_bundle(d, net)
        layout = LAYOUTS.get(net)
        shapes = {}
        if layout:
            for fname in layout.required_files:
                fp = d / fname
                if fp.is_file():
                    arr = np.load(fp)
                    shapes[fname] = {"shape": list(arr.shape), "dtype": str(arr.dtype)}
        bundles.append(
            {
                "path": str(d),
                "network": net,
                "valid": ok,
                "errors": errs,
                "arrays": shapes,
            }
        )
    return {"source": "ahe_npy_bundles_on_disk", "bundles": bundles}


def main() -> int:
    index = 0
    analyzers = [
        ("official_idx", lambda: analyze_official_idx(index)),
        ("hf_mnist", lambda: analyze_hf_mnist(index)),
        ("kaggle_csv", lambda: analyze_kaggle_csv_style(index)),
        ("png_upload", lambda: analyze_png_upload(index)),
        ("npy_bundles", analyze_model_npy_bundle),
    ]
    formats = []
    for name, fn in analyzers:
        try:
            formats.append(fn())
        except Exception as exc:
            formats.append({"source": name, "error": repr(exc)})
    report = {
        "generated_at": _now(),
        "mnist_index": index,
        "formats": formats,
        "vpin_pipeline": {
            "steps": [
                "uint8 (28,28)",
                "/255 float",
                "pad to (1,1,32,32)",
                "per-image min-max clip [0, 1]",
                "× 2^16 → int32",
                "SHA256 → input_digest_hex",
            ],
            "constants": {
                "PAD_SIZE": 32,
                "INPUT_HW": 28,
                "FIXED_POINT_BITS": 16,
            },
        },
    }
    out_dir = REPO / "reports"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "dataset_format_analysis.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    for fmt in report["formats"]:
        name = fmt.get("source", "?")
        if "error" in fmt:
            print(f"  {name}: ERROR {fmt['error']}")
        elif name == "ahe_npy_bundles_on_disk":
            print(f"  {name}: {len(fmt.get('bundles', []))} bundle(s)")
        else:
            match = fmt.get("digest_match") or fmt.get("vpin_digest_match_official")
            print(f"  {name}: digest_match={match}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
