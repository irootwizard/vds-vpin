"""Rewrite FC PtMul weight slots using client gamma_mult (paper Eq. 10 RLC columns)."""

from __future__ import annotations

import struct

# Network A paper_proof layout
FC1_START = 18
FC1_END = 146
FC2_START = 146
FC2_END = 178
FC1_INPUTS = 64
FC2_INPUTS = 16
FC1_OUTPUTS = 16
FC2_OUTPUTS = 10
O_FC1 = 9
O_FC2 = 1049
ELGAMAL_BRANCHES = 2
MOD = 2**252 + 27742317777372353535851937790883648493


def _hex_to_wide_le(hex_str: str) -> bytes:
    h = hex_str.removeprefix("0x").strip()
    raw = bytes.fromhex(h)
    wide = bytearray(64)
    wide[: min(len(raw), 64)] = raw[:64]
    return bytes(wide)


def _embed_u128_to_field(value: int) -> int:
    wide = struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF) + b"\x00" * 56
    # Simplified mod for Python pre-check; Rust uses libspartan Scalar
    n = int.from_bytes(wide[:32], "little") % MOD
    return n


def _fold_rlc_row(row: list[int], gamma_wide: bytes) -> int:
    acc = 0
    pow_val = 1
    gamma = int.from_bytes(gamma_wide[:32], "little") % MOD
    for w in row:
        acc = (acc + pow_val * _embed_u128_to_field(w)) % MOD
        pow_val = (pow_val * gamma) % MOD
    return acc


def _fc_rlc_column(w_star: list[int], base: int, p: int, output_dim: int, gamma_wide: bytes) -> int:
    row = w_star[base + p * output_dim : base + (p + 1) * output_dim]
    return _fold_rlc_row(row, gamma_wide)


def apply_gamma_mult_to_fc_weights(
    weights: list[int],
    w_star: list[int],
    gamma_mult_hex: str,
) -> list[int]:
    """Replace FC segments of PtMul weight.json with gamma_mult RLC columns."""
    out = list(weights)
    gamma_wide = _hex_to_wide_le(gamma_mult_hex)

    for branch in range(ELGAMAL_BRANCHES):
        for p in range(FC1_INPUTS):
            j = FC1_START + branch * FC1_INPUTS + p
            out[j] = _fc_rlc_column(w_star, O_FC1, p, FC1_OUTPUTS, gamma_wide)
        for p in range(FC2_INPUTS):
            j = FC2_START + branch * FC2_INPUTS + p
            out[j] = _fc_rlc_column(w_star, O_FC2, p, FC2_OUTPUTS, gamma_wide)

    return out
