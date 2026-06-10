"""Minimal CLI entry for vpin-client."""

from __future__ import annotations

import argparse
import json
import sys

from vpin_client.crypto.challenge import sample_challenge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vpin-client", description="vPIN client tools")
    sub = parser.add_subparsers(dest="cmd")

    ch = sub.add_parser("sample-challenge", help="Sample P4 ClientChallenge (CSPRNG)")
    ch.add_argument("--num-pt-add", type=int, default=0)
    ch.add_argument("--num-pt-mult", type=int, default=0)

    args = parser.parse_args(argv)
    if args.cmd == "sample-challenge":
        c = sample_challenge(args.num_pt_add, args.num_pt_mult)
        print(
            json.dumps(
                {
                    "gamma": c.gamma,
                    "gamma_add": c.gamma_add,
                    "gamma_mult": c.gamma_mult,
                    "num_pt_add": c.num_pt_add,
                    "num_pt_mult": c.num_pt_mult,
                },
                indent=2,
            )
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
