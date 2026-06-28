"""CLI entry: train | export | register | evaluate."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m model_training.network_a [train|export|register|evaluate] ...")
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "train":
        from model_training.network_a.train import main as train_main

        return train_main(rest)
    if cmd == "export":
        from model_training.network_a.export_weights import main as export_main

        return export_main(rest)
    if cmd == "register":
        from model_training.network_a.register_backend import main as register_main

        return register_main(rest)
    if cmd == "evaluate":
        from model_training.network_a.evaluate import main as evaluate_main

        return evaluate_main(rest)
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
