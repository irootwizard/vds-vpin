"""Backend-owned M1 / RLC unit tests (migrated from vpin-client)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_backend.crypto.challenge import challenge_from_hex
from vpin_backend.proof.verify.conv import ConvLayerProofSpec, verify_conv_eq9_rlc_only
from vpin_backend.proof.verify.rlc import (
    conv_rlc_left,
    conv_rlc_right,
    embed_u128_to_scalar,
    fold_rlc,
    scalar_from_hex,
)

CONV_TRACE = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "conv_trace.json"
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


def test_embed_u128_to_scalar() -> None:
    assert embed_u128_to_scalar(0) == 0
    assert embed_u128_to_scalar(48) == 48


def test_fold_rlc_manual_two_terms() -> None:
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    values = [10, 20]
    expected = (
        embed_u128_to_scalar(10)
        + (gamma * embed_u128_to_scalar(20)) % (1 << 256)
    )
    assert fold_rlc(values, gamma) == expected % int(
        "1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed", 16
    )


@pytest.mark.skipif(not CONV_TRACE.is_file(), reason="Network A conv_trace.json missing")
def test_conv_rlc_network_a_eq9_holds() -> None:
    spec = _load_conv_trace()
    gamma = scalar_from_hex(TEST_GAMMA_HEX)
    assert conv_rlc_left(spec.output_flat, gamma) == conv_rlc_right(
        spec.filter_flat, spec.windows, gamma
    )


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
