"""Dataset catalog API — metadata only (no plaintext pixels on server)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["datasets"])

# Placeholder remote catalogs removed — client loads local datasets only.
_REMOTE_CATALOG: list = []

_LOCAL_CATALOG = [
    {
        "id": "mnist-test",
        "name": "MNIST 官方测试集",
        "kind": "image",
        "location": "local",
        "format": "idx_uint8_28x28",
        "sample_count": 10_000,
        "index_range": [0, 9999],
        "cache_path_hint": "model_training/data/MNIST/raw",
        "previewable": True,
        "preview_samples": [
            {"index": 0, "label": None, "thumbnail_key": "mnist-0"},
            {"index": 1, "label": None, "thumbnail_key": "mnist-1"},
            {"index": 2, "label": None, "thumbnail_key": "mnist-2"},
            {"index": 3, "label": None, "thumbnail_key": "mnist-3"},
            {"index": 4, "label": None, "thumbnail_key": "mnist-4"},
        ],
        "message": "明文 IDX 仅在本机 vpin_client / Tauri 加载",
    },
    {
        "id": "mnist-train",
        "name": "MNIST 官方训练集",
        "kind": "image",
        "location": "local",
        "format": "idx_uint8_28x28",
        "sample_count": 60_000,
        "index_range": [0, 59999],
        "cache_path_hint": "model_training/data/MNIST/raw",
        "previewable": True,
        "preview_samples": [
            {"index": 0, "label": None, "thumbnail_key": "mnist-5"},
            {"index": 1, "label": None, "thumbnail_key": "mnist-6"},
        ],
        "message": "用于 model_training；AHE 演示默认使用 test 集",
    },
    {
        "id": "cifar10-test",
        "name": "CIFAR-10 官方测试集",
        "kind": "image",
        "location": "local",
        "format": "rgb_uint8_32x32",
        "sample_count": 10_000,
        "index_range": [0, 9999],
        "cache_path_hint": "model_training/data/cifar10",
        "previewable": True,
        "preview_samples": [
            {"index": 0, "label": None, "thumbnail_key": "cifar-0"},
            {"index": 1, "label": None, "thumbnail_key": "cifar-1"},
        ],
        "message": "RGB 32×32，LeNet / ResNet 密态推理",
    },
    {
        "id": "cifar10-train",
        "name": "CIFAR-10 官方训练集",
        "kind": "image",
        "location": "local",
        "format": "rgb_uint8_32x32",
        "sample_count": 50_000,
        "index_range": [0, 49999],
        "cache_path_hint": "model_training/data/cifar10",
        "previewable": True,
        "preview_samples": [],
        "message": "用于 model_training；预览在客户端本地加载",
    },
    {
        "id": "user-upload-image",
        "name": "本地上传图像",
        "kind": "image",
        "location": "local",
        "format": "png_jpeg_webp",
        "sample_count": None,
        "previewable": True,
        "dynamic": True,
        "preview_samples": [],
        "message": "在下方「上传本地文件」或「图像精度预处理」中选择",
    },
]


@router.get("/datasets/catalog")
def datasets_catalog() -> dict:
    """Return local + remote dataset metadata (no pixel payloads)."""
    return {
        "local": _LOCAL_CATALOG,
        "remote": _REMOTE_CATALOG,
    }


@router.get("/datasets/remote")
def datasets_remote() -> dict:
    """Remote dataset entries only (placeholder)."""
    return {"items": _REMOTE_CATALOG, "count": len(_REMOTE_CATALOG)}
