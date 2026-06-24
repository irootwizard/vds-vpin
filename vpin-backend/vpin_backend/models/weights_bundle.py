"""Install and validate AHE npy weight bundles on the server."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
_CLIENT = _REPO / "vpin-client"
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from vpin_client.models.format_adapter import validate_npy_bundle
from vpin_client.models.weights_layout import get_layout


def resolve_weights_dir(entry: dict, default: Path) -> Path:
    for key in ("weights_dir", "weight_dir", "storage_path"):
        val = entry.get(key)
        if val:
            p = Path(val)
            if p.is_dir() and _has_any_npy(p):
                return p
    return default


def _has_any_npy(directory: Path) -> bool:
    return any(directory.glob("*.npy"))


def load_homomorphic_weights(weights_dir: Path, network: str = "A"):
    """Load FC weights for homomorphic inference (Network A/B share conv+pool path)."""
    from vpin_backend.inference.homomorphic_network_a import NetworkAWeights

    layout = get_layout(network)
    ok, errs = validate_npy_bundle(weights_dir, network)
    if not ok:
        raise FileNotFoundError(f"invalid bundle in {weights_dir}: {errs}")
    return NetworkAWeights(
        weight_fc1=np.load(weights_dir / layout.weight_fc1),
        bias_fc1=np.load(weights_dir / layout.bias_fc1),
        weight_fc2=np.load(weights_dir / layout.weight_fc2),
        bias_fc2=np.load(weights_dir / layout.bias_fc2),
    )


def install_bundle(source: Path, dest: Path, network: str) -> Path:
    layout = get_layout(network)
    dest.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for fname in layout.required_files:
            (dest / fname).write_bytes((source / fname).read_bytes())
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            for fname in layout.required_files:
                member = next((n for n in zf.namelist() if Path(n).name == fname), None)
                if member is None:
                    raise FileNotFoundError(fname)
                dest.joinpath(fname).write_bytes(zf.read(member))
    else:
        raise ValueError(f"unsupported bundle source: {source}")
    ok, errs = validate_npy_bundle(dest, network)
    if not ok:
        raise ValueError("; ".join(errs))
    return dest


def weights_digest(weights_dir: Path, network: str = "A") -> str:
    import hashlib

    layout = get_layout(network)
    h = hashlib.sha256()
    for name in sorted(layout.required_files):
        path = weights_dir / name
        if path.is_file():
            h.update(path.read_bytes())
    return h.hexdigest()
