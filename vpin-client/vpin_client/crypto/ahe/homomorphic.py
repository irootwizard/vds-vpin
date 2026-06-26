"""Homomorphic add / scalar multiply on exponential ElGamal ciphertexts."""

from __future__ import annotations

from ecdsa.ellipticcurve import Point


def homomorphic_add(c1_a: Point, c2_a: Point, c1_b: Point, c2_b: Point) -> tuple[Point, Point]:
    return c1_a + c1_b, c2_a + c2_b


def homomorphic_scalar_mul(k: int, c1: Point, c2: Point) -> tuple[Point, Point]:
    return k * c1, k * c2
