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

from vpin_client.models.format_adapter import validate_lenet_npy_bundle, validate_npy_bundle
from vpin_client.models.lenet_weights_layout import get_lenet_layout
from vpin_client.models.weights_layout import get_layout, is_lenet_cifar


def _repo_root() -> Path:
    from vpin_backend.config import get_settings

    return get_settings().repo_root.resolve()


def normalize_weights_path(raw: str | Path, *, repo_root: Path | None = None) -> Path:
    """Resolve a stored weights_dir (absolute or repo-relative) on this machine."""
    root = (repo_root or _repo_root()).resolve()
    p = Path(raw)
    if p.is_absolute() and p.is_dir():
        return p.resolve()
    if not p.is_absolute():
        candidate = (root / p).resolve()
        if candidate.is_dir():
            return candidate
    if p.is_absolute():
        for marker in ("model_training", "src"):
            if marker in p.parts:
                idx = p.parts.index(marker)
                candidate = (root / Path(*p.parts[idx:])).resolve()
                if candidate.is_dir():
                    return candidate
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def store_weights_path(weights_dir: Path, *, repo_root: Path | None = None) -> str:
    """Serialize weights_dir for registry — prefer repo-relative forward-slash path."""
    root = (repo_root or _repo_root()).resolve()
    wd = Path(weights_dir).resolve()
    try:
        return wd.relative_to(root).as_posix()
    except ValueError:
        return str(wd)


def resolve_weights_dir(entry: dict, default: Path) -> Path:
    root = _repo_root()
    fallback = Path(default).resolve()
    for key in ("weights_dir", "weight_dir", "storage_path"):
        val = entry.get(key)
        if not val:
            continue
        p = normalize_weights_path(val, repo_root=root)
        if p.is_dir() and _has_any_npy(p):
            return p
    return fallback


def _has_any_npy(directory: Path) -> bool:
    return any(directory.glob("*.npy"))


def load_homomorphic_weights(weights_dir: Path, network: str = "A"):
    """Load weights for homomorphic inference (Network A/B or LeNet)."""
    if is_lenet_cifar(network):
        from vpin_backend.inference.homomorphic_network_lenet import load_lenet_weights

        lkey = network.lower().replace("-", "_")
        variant = "mnist" if lkey == "lenet_mnist" else "cifar"
        return load_lenet_weights(weights_dir, variant=variant)

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


def _lenet_variant(network: str) -> str:
    return "mnist" if network.lower().replace("-", "_") == "lenet_mnist" else "cifar"


def install_bundle(source: Path, dest: Path, network: str) -> Path:
    if is_lenet_cifar(network):
        layout = get_lenet_layout(variant=_lenet_variant(network))
    else:
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

    if is_lenet_cifar(network):
        layout = get_lenet_layout(variant=_lenet_variant(network))
        files = layout.required_files
    else:
        layout = get_layout(network)
        files = layout.required_files
    h = hashlib.sha256()
    for name in sorted(files):
        path = weights_dir / name
        if path.is_file():
            h.update(path.read_bytes())
    return h.hexdigest()
