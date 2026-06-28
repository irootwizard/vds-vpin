"""CLI entry: train | export | register | verify | evaluate."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m model_training.network_lenet [train|export|register|verify|evaluate] ...")
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "train":
        from model_training.network_lenet.train import main as m

        return m(rest)
    if cmd == "export":
        from model_training.network_lenet.export_weights import main as m

        return m(rest)
    if cmd == "register":
        from model_training.network_lenet.register_backend import main as m

        return m(rest)
    if cmd == "verify":
        from model_training.network_lenet.verify import main as m

        return m(rest)
    if cmd == "evaluate":
        from model_training.network_lenet.evaluate import main as m

        return m(rest)
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
