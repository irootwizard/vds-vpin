"""Client AHE keygen / encrypt / decrypt tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from vpin_client.crypto.ahe import (
    decrypt_ciphertext_pair,
    encrypt_scalar,
    homomorphic_add,
    key_gen,
    load_bsgs_table,
)

REPO = Path(__file__).resolve().parents[2]
BSGS = REPO / "src" / "Pre_computed_table" / "table.pickle"


def test_keygen_produces_valid_keys() -> None:
    keys = key_gen()
    assert keys.private_scalar > 0
    assert keys.public_key != keys.generator * 0


def test_encrypt_decrypt_roundtrip() -> None:
    if not BSGS.is_file():
        pytest.skip("BSGS table missing")
    table = load_bsgs_table(BSGS)
    keys = key_gen()
    m = 12345
    c1, c2 = encrypt_scalar(
        m,
        generator=keys.generator,
        public_key=keys.public_key,
        curve_order=keys.curve_order,
    )
    dec = decrypt_ciphertext_pair(keys.private_scalar, c1, c2, keys.generator, table)
    assert dec == m


def test_homomorphic_add() -> None:
    if not BSGS.is_file():
        pytest.skip("BSGS table missing")
    table = load_bsgs_table(BSGS)
    keys = key_gen()
    m1, m2 = 100, 200
    c1a, c2a = encrypt_scalar(
        m1,
        generator=keys.generator,
        public_key=keys.public_key,
        curve_order=keys.curve_order,
    )
    c1b, c2b = encrypt_scalar(
        m2,
        generator=keys.generator,
        public_key=keys.public_key,
        curve_order=keys.curve_order,
    )
    c1s, c2s = homomorphic_add(c1a, c2a, c1b, c2b)
    dec = decrypt_ciphertext_pair(keys.private_scalar, c1s, c2s, keys.generator, table)
    assert dec == m1 + m2
