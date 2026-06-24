"""Bootstrap AHE model registry and legacy weights on server startup."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vpin_backend.config import get_settings
from vpin_backend.storage.registry import get_model, upsert_model


def _has_npy_bundle(directory: Path, network: str) -> bool:
    from vpin_client.models.weights_layout import get_layout

    layout = get_layout(network)
    return all((directory / name).is_file() for name in layout.required_files)


def _restore_legacy_weights() -> Path | None:
    settings = get_settings()
    out_dir = settings.cnn_networks_dir / "Pre_trained_model"
    if _has_npy_bundle(out_dir, "A"):
        return out_dir

    script = settings.repo_root / "scripts" / "restore_network_a_weights.py"
    json_path = settings.repo_root / "src" / "cp-snark-full" / "model_exports" / "A" / "full_weights.json"
    if not script.is_file() or not json_path.is_file():
        return None

    python = settings.repo_root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)

    subprocess.run(
        [str(python), str(script), "--json", str(json_path), "--out", str(out_dir)],
        check=False,
        cwd=str(settings.repo_root),
    )
    return out_dir if _has_npy_bundle(out_dir, "A") else None


def _register_builtin_legacy(weights_dir: Path) -> None:
    if get_model("cnn-mnist"):
        return
    upsert_model(
        {
            "id": "cnn-mnist",
            "name": "CNN (MNIST 预训练 / legacy)",
            "framework": "npy",
            "task": "图像分类",
            "params_count_m": 1.21,
            "input_shape": "1x28x28",
            "accuracy": 99.1,
            "network": "A",
            "topology": "cnn_mnist_v1",
            "weights_dir": str(weights_dir.resolve()),
        }
    )


def _register_from_output_runs() -> None:
    settings = get_settings()
    outputs = settings.repo_root / "model_training" / "outputs"
    if not outputs.is_dir():
        return

    candidates: list[tuple[float, Path, dict]] = []
    for run_dir in outputs.iterdir():
        if not run_dir.is_dir():
            continue
        snippet = run_dir / "registry_snippet.json"
        if snippet.is_file():
            entry = json.loads(snippet.read_text(encoding="utf-8"))
            weights_dir = Path(entry.get("weights_dir", run_dir))
        elif _has_npy_bundle(run_dir, "A"):
            weights_dir = run_dir
            entry = {"id": f"cnn-mnist-trained-{run_dir.name}", "network": "A"}
        else:
            continue

        if not _has_npy_bundle(weights_dir, entry.get("network", "A")):
            continue
        mtime = max(
            (weights_dir / "weight_fc1_64_16.npy").stat().st_mtime,
            snippet.stat().st_mtime if snippet.is_file() else 0,
        )
        candidates.append((mtime, weights_dir, entry))

    if not candidates:
        return

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, weights_dir, entry = candidates[0]
    model_id = entry.get("id", "cnn-mnist-trained")
    if get_model(model_id):
        return

    upsert_model(
        {
            **entry,
            "id": model_id,
            "weights_dir": str(weights_dir.resolve()),
            "framework": entry.get("framework", "npy"),
            "network": entry.get("network", "A"),
        }
    )


def bootstrap_ahe_models() -> None:
    """Ensure at least one AHE-capable model is registered."""
    legacy_dir = _restore_legacy_weights()
    if legacy_dir is not None:
        _register_builtin_legacy(legacy_dir)
    _register_from_output_runs()
