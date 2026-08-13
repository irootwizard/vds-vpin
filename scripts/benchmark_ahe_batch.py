#!/usr/bin/env python3
"""Wrapper: AHE batch concurrency stress test (see vpin_client.cli bench-mnist-ahe)."""

from vpin_client.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["bench-mnist-ahe", *__import__("sys").argv[1:]]))
