"""FC + stacked M1 verification tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vpin_client.crypto.challenge import challenge_from_hex
from vpin_client.verify.conv import ConvLayerProofSpec
from vpin_client.verify.fc import FcLayerProofSpec, verify_fc_eq10_rlc_only
from vpin_client.verify.pool import PoolLayerProofSpec
from vpin_client.verify.stack import ServerLinearProofStack, verify_all_client

REPO = Path(__file__).resolve().parents[2]
FC = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "fc_trace.json"
CONV = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "conv_trace.json"
POOL = REPO / "src" / "cp-snark-full" / "model_exports" / "A" / "pool_trace.json"

TEST_GAMMA_HEX = "02" + "00" * 31
TEST_GAMMA_ADD_HEX = "03" + "00" * 31
TEST_GAMMA_MULT_HEX = "05" + "00" * 31


@pytest.mark.skipif(not FC.is_file(), reason="fc_trace missing or F10 empty")
def test_fc_eq10_network_a() -> None:
    data = json.loads(FC.read_text(encoding="utf-8"))
    layers = data.get("layers") or []
    if not layers:
        pytest.skip("fc_trace layers empty")
    layer = layers[0]
    spec = FcLayerProofSpec(
        inputs=[int(x) for x in layer["inputs"]],
        weights_in_out=[[int(x) for x in row] for row in layer["weights_in_out"]],
        bias=[int(x) for x in layer["bias"]],
        outputs=[int(x) for x in layer["outputs"]],
    )
    ch = challenge_from_hex(
        TEST_GAMMA_HEX, TEST_GAMMA_ADD_HEX, TEST_GAMMA_MULT_HEX, 0, 0
    )
    verify_fc_eq10_rlc_only(spec, ch)


@pytest.mark.skipif(not CONV.is_file(), reason="trace vectors missing")
def test_verify_all_client_skip_fc() -> None:
    conv = json.loads(CONV.read_text(encoding="utf-8"))
    stack = ServerLinearProofStack(skip_fc=True)
    stack.conv_layers.append(
        ConvLayerProofSpec(
            filter_flat=[int(x) for x in conv["filter_flat"]],
            windows=[[int(x) for x in w] for w in conv["windows"]],
            output_flat=[int(x) for x in conv["output_flat"]],
        )
    )
    if POOL.is_file():
        pool = json.loads(POOL.read_text(encoding="utf-8"))
        sums = pool.get("output_sums") or pool.get("output_flat", [])
        stack.pool_layers.append(
            PoolLayerProofSpec(
                windows=[[int(x) for x in w] for w in pool["windows"]],
                output_sums=[int(x) for x in sums],
            )
        )
    ch = challenge_from_hex(
        TEST_GAMMA_HEX, TEST_GAMMA_ADD_HEX, TEST_GAMMA_MULT_HEX, 2144, 178
    )
    verify_all_client(stack, ch)
