#!/usr/bin/env python3
"""Smoke test: charm-crypto BN254 pairing is usable in this environment."""

from charm.toolbox.pairinggroup import PairingGroup, G1, G2, GT, ZR, pair


def main() -> None:
    group = PairingGroup("BN254")
    g1 = group.random(G1)
    g2 = group.random(G2)
    e = pair(g1, g2)
    zr = group.random(ZR)
    _ = g1 ** zr
    _ = group.random(GT)
    print("charm BN254 ok")
    print(f"  pairing type: {type(e).__name__}")


if __name__ == "__main__":
    main()
