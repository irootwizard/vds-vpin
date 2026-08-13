"""CLI entry: train ResNet-CIFAR."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "train":
        from model_training.network_resnet.train import main as m

        return m(argv[1:] if argv and argv[0] == "train" else argv)
    if argv[0] == "check-env":
        from model_training.network_resnet.check_env import main as m

        return m()
    print(f"unknown command: {argv[0]}")
    print("usage: python -m model_training.network_resnet [train|check-env] ...")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
