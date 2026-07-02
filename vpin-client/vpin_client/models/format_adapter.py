"""Detect and validate vPIN-compatible model weight formats."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from vpin_client.models.lenet_weights_layout import get_lenet_layout
from vpin_client.models.resnet_weights_layout import get_resnet_layout
from vpin_client.models.weights_layout import NetworkWeightLayout, get_layout, is_lenet_cifar, is_resnet


class ModelFormat(str, Enum):
    AHE_NPY_BUNDLE = "ahe_npy_bundle"
    MODEL_EXPORT_JSON = "model_export_json"
    CHECKPOINT_PT = "checkpoint_pt"
    UNKNOWN = "unknown"


@dataclass
class FormatProbe:
    format: ModelFormat
    network: str | None = None
    detail: str = ""
    missing_files: tuple[str, ...] = ()


def detect_format(path: Path) -> FormatProbe:
    path = path.resolve()
    if path.is_dir():
        return _probe_directory(path)
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _probe_zip(path)
    if suffix == ".json":
        return _probe_json(path)
    if suffix in (".pt", ".pth"):
        return FormatProbe(ModelFormat.CHECKPOINT_PT, detail="PyTorch checkpoint — export to npy for AHE")
    if suffix == ".npy":
        return FormatProbe(ModelFormat.UNKNOWN, detail="single npy — need full bundle directory")
    return FormatProbe(ModelFormat.UNKNOWN, detail=f"unsupported: {path.name}")


def _probe_json(path: Path) -> FormatProbe:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return FormatProbe(ModelFormat.UNKNOWN, detail=str(exc))
    if "conv_filter_flat" in data or "fc" in data:
        net = str(data.get("network_id", "A")).upper()
        return FormatProbe(ModelFormat.MODEL_EXPORT_JSON, network=net, detail="CP-SNARK model_export.json")
    return FormatProbe(ModelFormat.UNKNOWN, detail="json without vPIN export schema")


def _probe_directory(path: Path) -> FormatProbe:
    lenet_layout = get_lenet_layout()
    missing_lenet = [f for f in lenet_layout.required_files if not (path / f).is_file()]
    if not missing_lenet:
        return FormatProbe(
            ModelFormat.AHE_NPY_BUNDLE,
            network="lenet_cifar",
            detail="complete LeNet-CIFAR npy bundle",
        )
    for net in ("A", "B", "C", "D", "E"):
        layout = get_layout(net)
        missing = [f for f in layout.required_files if not (path / f).is_file()]
        if not missing:
            return FormatProbe(ModelFormat.AHE_NPY_BUNDLE, network=net, detail="complete npy bundle")
    return FormatProbe(ModelFormat.UNKNOWN, detail="directory missing required npy set for A–E or lenet_cifar")


def _probe_zip(path: Path) -> FormatProbe:
    with zipfile.ZipFile(path) as zf:
        names = {Path(n).name for n in zf.namelist() if not n.endswith("/")}
    for net in ("A", "B", "C", "D", "E"):
        layout = get_layout(net)
        missing = [f for f in layout.required_files if f not in names]
        if not missing:
            return FormatProbe(ModelFormat.AHE_NPY_BUNDLE, network=net, detail="zip npy bundle")
    return FormatProbe(ModelFormat.UNKNOWN, detail="zip missing npy files for A–E")


def validate_resnet_npy_bundle(directory: Path) -> tuple[bool, list[str]]:
    directory = Path(directory)
    layout = get_resnet_layout()
    errors: list[str] = []
    for fname in layout.required_files:
        p = directory / fname
        if not p.is_file():
            errors.append(f"missing {fname}")
            continue
        arr = np.load(p)
        if arr.size == 0:
            errors.append(f"empty {fname}")
    return len(errors) == 0, errors


def validate_npy_bundle(directory: Path, network: str) -> tuple[bool, list[str]]:
    if is_resnet(network):
        return validate_resnet_npy_bundle(directory)
    if is_lenet_cifar(network):
        lkey = network.lower().replace("-", "_")
        variant = "mnist" if lkey == "lenet_mnist" else "cifar"
        return validate_lenet_npy_bundle(directory, variant=variant)
    layout = get_layout(network)
    errors: list[str] = []
    for fname in layout.required_files:
        p = directory / fname
        if not p.is_file():
            errors.append(f"missing {fname}")
            continue
        arr = np.load(p)
        if arr.size == 0:
            errors.append(f"empty {fname}")
    w1 = directory / layout.weight_fc1
    if w1.is_file():
        w = np.load(w1)
        if w.shape != (layout.fc1_in, layout.fc1_out):
            errors.append(f"{layout.weight_fc1} shape {w.shape} != ({layout.fc1_in}, {layout.fc1_out})")
    return len(errors) == 0, errors


def validate_lenet_npy_bundle(directory: Path, variant: str = "cifar") -> tuple[bool, list[str]]:
    layout = get_lenet_layout(variant=variant)
    errors: list[str] = []
    for fname in layout.required_files:
        p = directory / fname
        if not p.is_file():
            errors.append(f"missing {fname}")
            continue
        arr = np.load(p)
        if arr.size == 0:
            errors.append(f"empty {fname}")
    return len(errors) == 0, errors


def install_npy_bundle(
    source: Path,
    dest: Path,
    *,
    network: str,
) -> Path:
    """Copy or extract npy bundle into dest; returns dest."""
    layout = get_layout(network)
    dest.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for fname in layout.required_files:
            shutil_copy(source / fname, dest / fname)
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            for fname in layout.required_files:
                member = next((n for n in zf.namelist() if Path(n).name == fname), None)
                if member is None:
                    raise FileNotFoundError(fname)
                dest.joinpath(fname).write_bytes(zf.read(member))
    else:
        raise ValueError(f"cannot install from {source}")
    ok, errs = validate_npy_bundle(dest, network)
    if not ok:
        raise ValueError("; ".join(errs))
    return dest


def shutil_copy(src: Path, dst: Path) -> None:
    dst.write_bytes(src.read_bytes())
