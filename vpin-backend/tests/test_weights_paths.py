"""Registry weights_dir path resolution (portable across machines)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))
sys.path.insert(0, str(REPO / "vpin-client"))

from vpin_backend.config import get_settings
from vpin_backend.models.weights_bundle import (
    normalize_weights_path,
    resolve_weights_dir,
    store_weights_path,
)


def test_store_weights_path_relative() -> None:
    settings = get_settings()
    run = settings.repo_root / "model_training" / "outputs" / "20260622_184254"
    if not run.is_dir():
        pytest.skip("trained run not present")
    stored = store_weights_path(run, repo_root=settings.repo_root)
    assert not Path(stored).is_absolute()
    assert stored.replace("\\", "/") == "model_training/outputs/20260622_184254"


def test_normalize_stale_absolute_path() -> None:
    settings = get_settings()
    run = settings.repo_root / "model_training" / "outputs" / "20260622_184254"
    if not run.is_dir():
        pytest.skip("trained run not present")
    stale = Path("D:/other/machine") / "model_training" / "outputs" / "20260622_184254"
    resolved = normalize_weights_path(stale, repo_root=settings.repo_root)
    assert resolved == run.resolve()


def test_resolve_weights_dir_from_registry_entry() -> None:
    settings = get_settings()
    run = settings.repo_root / "model_training" / "outputs" / "20260622_184254"
    default = settings.cnn_networks_dir / "Pre_trained_model"
    if not run.is_dir():
        pytest.skip("trained run not present")
    entry = {"weights_dir": "model_training/outputs/20260622_184254"}
    assert resolve_weights_dir(entry, default) == run.resolve()
    stale_entry = {
        "weights_dir": "D:\\WorkStation\\pythoncode\\experiment-reproduction\\vPIN-main\\model_training\\outputs\\20260622_184254"
    }
    assert resolve_weights_dir(stale_entry, default) == run.resolve()
