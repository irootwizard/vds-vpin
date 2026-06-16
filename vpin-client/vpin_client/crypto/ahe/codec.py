"""Encrypt / decrypt / fixed-point — semantic port of Client.py."""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Any

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_client.crypto.ahe.curve import KeyMaterial


def real_to_fixed_point(values: np.ndarray, bits: int = 16) -> np.ndarray:
    scale = 2**bits
    return (values * scale).astype(np.int32)


def fixed_point_to_real(values: np.ndarray, bits: int) -> np.ndarray:
    scale = 2**bits
    return np.array(values, dtype=np.float32) / scale


def encrypt_scalar(
    plaintext: int,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[Point, Point]:
    r = random.randrange(1, curve_order - 1)
    m = int(plaintext)
    c1 = r * generator
    c2 = m * generator + r * public_key
    return c1, c2


def encrypt_tensor(
    tensor: np.ndarray,
    keys: KeyMaterial,
    layout: str = "4d",
) -> tuple[np.ndarray, np.ndarray]:
    if layout == "4d":
        shape = tensor.shape
        c1 = np.empty(shape, dtype=object)
        c2 = np.empty(shape, dtype=object)
        for i in range(shape[0]):
            for j in range(shape[1]):
                for k in range(shape[2]):
                    for l in range(shape[3]):
                        c1[i, j, k, l], c2[i, j, k, l] = encrypt_scalar(
                            int(tensor[i, j, k, l]),
                            generator=keys.generator,
                            public_key=keys.public_key,
                            curve_order=keys.curve_order,
                        )
    else:
        rows, cols = tensor.shape
        c1 = np.empty((rows, cols), dtype=object)
        c2 = np.empty((rows, cols), dtype=object)
        for i in range(rows):
            for j in range(cols):
                c1[i, j], c2[i, j] = encrypt_scalar(
                    int(tensor[i, j]),
                    generator=keys.generator,
                    public_key=keys.public_key,
                    curve_order=keys.curve_order,
                )
    return c1, c2


def _giant_step(alpha: Point, beta: Point, beta_neg: Point, table: dict) -> int:
    m = 3_200_000
    inv_alpha_m = -m * alpha
    gamma = beta
    gamma2 = beta_neg
    for i in range(m):
        key = (gamma.x(), gamma.y())
        if key in table:
            return i * m + table[key]
        key2 = (gamma2.x(), gamma2.y())
        if key2 in table:
            return -(i * m + table[key2])
        gamma = gamma + inv_alpha_m
        gamma2 = gamma2 + inv_alpha_m
    raise ValueError("discrete log not found in BSGS table range")


def decrypt_ciphertext_pair(
    private_scalar: int,
    c1: Point,
    c2: Point,
    generator: Point,
    table: dict,
) -> int:
    s = private_scalar * c1
    output = c2 + ((-1) * s)
    s2 = private_scalar * ((-1) * c1)
    output2 = ((-1) * c2) + ((-1) * s2)
    return _giant_step(generator, output, output2, table)


def load_bsgs_table(path: Path) -> dict[Any, int]:
    with path.open("rb") as f:
        return pickle.load(f)
