"""RLC unit tests — Network A conv trace vectors (cp-snark-full model_exports/A)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vpin_client.crypto.challenge import challenge_from_hex
from vpin_client.verify.conv import ConvLayerProofSpec, verify_conv_eq9_rlc_only
from vpin_client.verify.rlc import (
    E1_FIELD_MODULUS,
    conv_rlc_left,
    conv_rlc_right,
    embed_u128_to_scalar,
    fold_rlc,
    scalar_from_hex,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONV_TRACE = REPO_ROOT / "src" / "cp-snark-full" / "model_exports" / "A" / "conv_trace.json"

# Deterministic 32-byte challenge (test-only)
TEST_GAMMA_HEX = "02" + "00" * 31
TEST_GAMMA_ADD_HEX = "03" + "00" * 31
TEST_GAMMA_MULT_HEX = "05" + "00" * 31


def _load_conv_trace() -> ConvLayerProofSpec:
    data = json.loads(CONV_TRACE.read_text(encoding="utf-8"))
    return ConvLayerProofSpec(
        filter_flat=[int(x) for x in data["filter_flat"]],
        windows=[[int(x) for x in w] for w in data["windows"]],
        output_flat=[int(x) for x in data["output_flat"]],
    )


def test_embed_u128_matches_small_integers() -> None:
    assert embed_u128_to_scalar(0) == 0
    assert embed_u128_to_scalar(48) == 48
    assert embed_u128_to_scalar(2**128 - 1) == 2**128 - 1


def test_fold_rlc_empty() -> None:
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    assert fold_rlc([], gamma) == 0


def test_fold_rlc_single_term() -> None:
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    assert fold_rlc([42], gamma) == embed_u128_to_scalar(42)


def test_fold_rlc_gamma_one_is_sum() -> None:
    gamma = 1
    values = [3, 5, 7]
    expected = sum(embed_u128_to_scalar(v) for v in values) % E1_FIELD_MODULUS
    assert fold_rlc(values, gamma) == expected


def test_fold_rlc_manual_two_terms() -> None:
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    values = [10, 20]
    expected = (
        embed_u128_to_scalar(10)
        + (gamma * embed_u128_to_scalar(20)) % E1_FIELD_MODULUS
    ) % E1_FIELD_MODULUS
    assert fold_rlc(values, gamma) == expected


@pytest.mark.skipif(not CONV_TRACE.is_file(), reason="Network A conv_trace.json missing")
def test_conv_rlc_network_a_eq9_holds() -> None:
    spec = _load_conv_trace()
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    left = conv_rlc_left(spec.output_flat, gamma)
    right = conv_rlc_right(spec.filter_flat, spec.windows, gamma)
    assert left == right


@pytest.mark.skipif(not CONV_TRACE.is_file(), reason="Network A conv_trace.json missing")
def test_verify_conv_eq9_rlc_only_network_a() -> None:
    spec = _load_conv_trace()
    challenge = challenge_from_hex(
        TEST_GAMMA_HEX,
        TEST_GAMMA_ADD_HEX,
        TEST_GAMMA_MULT_HEX,
        num_pt_add=0,
        num_pt_mult=0,
    )
    verify_conv_eq9_rlc_only(spec, challenge)
