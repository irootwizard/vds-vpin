"""Export conv/pool/fc trace JSON for client M1 verification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vpin_backend.config import get_settings


def model_exports_dir(network: str) -> Path:
    return get_settings().repo_root / "src" / "cp-snark-full" / "model_exports" / network


def export_traces(network: str = "A") -> dict[str, Path]:
    """Return paths to trace JSON files (export via cp-snark-full python scripts if missing)."""
    out_dir = model_exports_dir(network)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "conv": out_dir / "conv_trace.json",
        "pool": out_dir / "pool_trace.json",
        "fc": out_dir / "fc_trace.json",
    }
    py_dir = get_settings().repo_root / "src" / "cp-snark-full" / "python"
    scripts = [
        ("conv", py_dir / "export_conv_trace_plaintext.py"),
        ("pool_fc", py_dir / "export_pool_fc_trace_plaintext.py"),
    ]
    for key, script in scripts:
        if script.is_file() and key == "conv" and not paths["conv"].is_file():
            subprocess.run(
                [sys.executable, str(script), network],
                cwd=str(script.parent),
                check=False,
            )
        if script.is_file() and key == "pool_fc":
            if not paths["pool"].is_file() or not paths["fc"].is_file():
                subprocess.run(
                    [sys.executable, str(script), network],
                    cwd=str(script.parent),
                    check=False,
                )
    return paths


def load_trace_bundle(network: str = "A") -> dict[str, object]:
    paths = export_traces(network)
    bundle: dict[str, object] = {}
    for name, path in paths.items():
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if name == "fc" and isinstance(data, dict) and not data.get("layers"):
                data = _synthetic_fc_from_conv(paths.get("conv"))
            bundle[name] = data
    return bundle


def _synthetic_fc_from_conv(conv_path: Path | None) -> dict[str, object]:
    """MVP placeholder when fc_trace.layers is empty (F10)."""
    if conv_path and conv_path.is_file():
        conv = json.loads(conv_path.read_text(encoding="utf-8"))
        flat = conv.get("output_flat") or []
        if flat:
            return {
                "layers": [
                    {
                        "inputs": flat[: min(len(flat), 128)],
                        "weights_in_out": [[1] * min(len(flat), 128)],
                        "bias": [0],
                        "outputs": [sum(flat[: min(len(flat), 128)])],
                    }
                ]
            }
    return {"layers": []}
