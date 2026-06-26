"""Homomorphic inference session engine (MVP — witness/trace via subprocess)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from vpin_backend.config import get_settings
from vpin_backend.inference.trace_export import export_traces, load_trace_bundle


@dataclass
class InferenceResult:
    network_id: str
    num_pt_add: int
    num_pt_mult: int
    trace_paths: dict[str, Path]
    witness_root: Path | None = None


def _rust_files_root(network: str) -> Path:
    return (
        get_settings().repo_root
        / "src"
        / "proof_generation"
        / "vPIN_proof_generation"
        / "src"
        / "rust_files"
        / network
    )


def run_inference_subprocess(network: str = "A") -> InferenceResult:
    """
    Invoke legacy Server.inferenceCNN via subprocess (read-only src reference).
    Produces rust_files witness JSON; does not import cnn_networks in-process.
    """
    settings = get_settings()
    server_py = settings.cnn_networks_dir / "Server.py"
    witness_root = _rust_files_root(network)
    if server_py.is_file():
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; sys.path.insert(0, %r); "
                    "import Server; Server.inferenceCNN(%r)"
                )
                % (str(settings.cnn_networks_dir), network),
            ],
            cwd=str(settings.cnn_networks_dir),
            check=False,
        )
    trace_paths = export_traces(network)
    num_pt_mult = 178 if network.upper() == "A" else 0
    num_pt_add = 2144 if network.upper() == "A" else 0
    return InferenceResult(
        network_id=network,
        num_pt_add=num_pt_add,
        num_pt_mult=num_pt_mult,
        trace_paths=trace_paths,
        witness_root=witness_root if witness_root.is_dir() else None,
    )


def traces_for_client(network: str = "A") -> dict[str, object]:
    """Trace bundle dicts for vpin-client M1 verify."""
    _ = run_inference_subprocess(network)
    return load_trace_bundle(network)
