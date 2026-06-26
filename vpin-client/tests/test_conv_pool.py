"""Conv + pool M1 scalar verification tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vpin_client.crypto.challenge import challenge_from_hex
from vpin_client.verify.conv import ConvLayerProofSpec, verify_conv_eq9_rlc_only
from vpin_client.verify.pool import PoolLayerProofSpec, verify_pool_eq7

REPO = Path(__file__).resolve().parents[2]
EXPORTS = REPO / "src" / "cp-snark-full" / "model_exports" / "A"
CONV = EXPORTS / "conv_trace.json"
POOL = EXPORTS / "pool_trace.json"

TEST_GAMMA_HEX = "02" + "00" * 31
TEST_GAMMA_ADD_HEX = "03" + "00" * 31
TEST_GAMMA_MULT_HEX = "05" + "00" * 31


@pytest.mark.skipif(not CONV.is_file(), reason="conv_trace missing")
def test_conv_eq9_network_a() -> None:
    data = json.loads(CONV.read_text(encoding="utf-8"))
    spec = ConvLayerProofSpec(
        filter_flat=[int(x) for x in data["filter_flat"]],
        windows=[[int(x) for x in w] for w in data["windows"]],
        output_flat=[int(x) for x in data["output_flat"]],
    )
    ch = challenge_from_hex(
        TEST_GAMMA_HEX, TEST_GAMMA_ADD_HEX, TEST_GAMMA_MULT_HEX, 0, 0
    )
    verify_conv_eq9_rlc_only(spec, ch)


@pytest.mark.skipif(not POOL.is_file(), reason="pool_trace missing")
def test_pool_eq7_network_a() -> None:
    data = json.loads(POOL.read_text(encoding="utf-8"))
    sums = data.get("output_sums") or data.get("output_flat", [])
    spec = PoolLayerProofSpec(
        windows=[[int(x) for x in w] for w in data["windows"]],
        output_sums=[int(x) for x in sums],
    )
    verify_pool_eq7(spec)
