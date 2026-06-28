"""Shared CUDA / CPU device helpers for model_training."""

from __future__ import annotations

import os
import random
from typing import Any

import numpy as np
import torch


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def default_num_workers() -> int:
    """Conservative DataLoader workers: Windows spawn-safe, higher on Linux + CUDA."""
    if not torch.cuda.is_available():
        return 0
    if os.name == "nt":
        return 2
    return min(4, os.cpu_count() or 1)


def configure_cuda_runtime() -> None:
    if not torch.cuda.is_available():
        return
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True


def amp_dtype(device: torch.device) -> torch.dtype:
    if device.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def cuda_environment() -> dict[str, Any]:
    info: dict[str, Any] = {
        "torch_version": torch.__version__,
        "cuda_compiled": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
    }
    if not torch.cuda.is_available():
        return info
    info["device_count"] = torch.cuda.device_count()
    info["device_name"] = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    info["compute_capability"] = f"{cap[0]}.{cap[1]}"
    info["bf16_supported"] = torch.cuda.is_bf16_supported()
    props = torch.cuda.get_device_properties(0)
    info["total_memory_gib"] = round(props.total_memory / (1024**3), 2)
    arch_list = []
    if hasattr(torch.cuda, "get_arch_list"):
        arch_list = list(torch.cuda.get_arch_list())
    info["compiled_arch_list"] = arch_list
    return info


def _warn_arch_mismatch(info: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not info.get("cuda_available"):
        return warnings
    cap = info.get("compute_capability", "")
    arch_list = info.get("compiled_arch_list") or []
    if not arch_list or not cap:
        return warnings
    major = int(str(cap).split(".")[0])
    # Blackwell sm_120+ may need PyTorch built with cu128 / 2.7+
    if major >= 12 and not any("120" in a or "12.0" in a for a in arch_list):
        warnings.append(
            "GPU compute capability >= 12.x (e.g. RTX 50 series) but current PyTorch "
            f"was not built for sm_120 (arch_list={arch_list}). "
            "Install a newer CUDA 12.8 wheel from https://pytorch.org — see "
            "model_training/requirements-gpu-rtx50.txt"
        )
    return warnings


def resolve_training_device(requested: str = "cuda") -> tuple[torch.device, dict[str, Any]]:
    """Pick device; fall back to CPU with a clear warning when CUDA is unavailable."""
    requested = requested.lower()
    info = cuda_environment()
    warnings = _warn_arch_mismatch(info)

    if requested == "cpu":
        dev = torch.device("cpu")
        info["device_used"] = "cpu"
        info["warnings"] = warnings
        return dev, info

    if requested.startswith("cuda"):
        if torch.cuda.is_available():
            configure_cuda_runtime()
            dev = torch.device(requested if ":" in requested else "cuda:0")
            info["device_used"] = str(dev)
            info["warnings"] = warnings
            return dev, info
        warnings.append(
            f"Requested device={requested!r} but torch.cuda.is_available() is False; using CPU. "
            "Install NVIDIA driver + CUDA-enabled PyTorch, then run: "
            "python -m model_training.network_resnet.check_env"
        )

    dev = torch.device("cpu")
    info["device_used"] = "cpu"
    info["warnings"] = warnings
    return dev, info


def print_device_report(info: dict[str, Any]) -> None:
    print("[device] torch", info.get("torch_version"), "cuda_compiled", info.get("cuda_compiled"))
    used = info.get("device_used", "unknown")
    print("[device] cuda_available", info.get("cuda_available"), "using", used)
    if info.get("cuda_available"):
        print(
            "[device]",
            info.get("device_name"),
            f"cc={info.get('compute_capability')}",
            f"mem={info.get('total_memory_gib')}GiB",
            f"bf16={info.get('bf16_supported')}",
        )
        if info.get("compiled_arch_list"):
            print("[device] compiled_arch_list", info["compiled_arch_list"])
    for w in info.get("warnings") or []:
        print(f"[device] WARNING: {w}")
