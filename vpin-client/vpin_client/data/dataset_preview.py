"""Route dataset preview loads by catalog id."""

from __future__ import annotations

from vpin_client.data.cifar10_official import load_cifar10_batch, load_cifar10_test
from vpin_client.data.core import preprocess_result_to_dict
from vpin_client.data.official import load_official_batch, load_official_test


def _mnist_dict(index: int, *, train: bool) -> dict:
    if train:
        from vpin_client.data.mnist_loader import fetch_mnist_train_sample
        from vpin_client.data.core import preprocess_uint8_28x28

        image, label = fetch_mnist_train_sample(index)
        result = preprocess_uint8_28x28(
            image,
            label=label,
            index=index,
            source="mnist-train",
        )
    else:
        result = load_official_test(index)
    out = preprocess_result_to_dict(result)
    out["dataset_id"] = "mnist-train" if train else "mnist-test"
    out["sample_index"] = index
    out["preview_kind"] = "grayscale"
    return out


def load_dataset_preview(dataset_id: str, index: int) -> dict:
    if dataset_id == "mnist-test":
        return _mnist_dict(index, train=False)
    if dataset_id == "mnist-train":
        return _mnist_dict(index, train=True)
    if dataset_id == "cifar10-test":
        return load_cifar10_test(index, train=False)
    if dataset_id == "cifar10-train":
        return load_cifar10_test(index, train=True)
    raise ValueError(f"unsupported dataset preview: {dataset_id}")


def load_dataset_batch(dataset_id: str, start: int, count: int) -> dict:
    if dataset_id == "mnist-test":
        items = [_mnist_dict(i, train=False) for i in range(start, min(start + count, 10_000))]
    elif dataset_id == "mnist-train":
        items = [_mnist_dict(i, train=True) for i in range(start, min(start + count, 60_000))]
    elif dataset_id == "cifar10-test":
        items = load_cifar10_batch(start, count, train=False)
    elif dataset_id == "cifar10-train":
        items = load_cifar10_batch(start, count, train=True)
    else:
        raise ValueError(f"unsupported dataset preview: {dataset_id}")
    return {"items": items}
