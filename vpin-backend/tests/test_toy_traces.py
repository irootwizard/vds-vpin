"""Hand-computed assertions for Phase Z toy trace vectors."""

from __future__ import annotations

import json
from pathlib import Path


TOY_DIR = Path(__file__).resolve().parents[1] / "data" / "toy"


def _load(name: str) -> dict:
    return json.loads((TOY_DIR / name).read_text(encoding="utf-8"))


def _ints(values: list[str]) -> list[int]:
    return [int(value) for value in values]


def test_toy_weights_are_frozen_for_z0() -> None:
    weights = _load("toy_full_weights.json")

    assert weights["network"] == "phase_z_toy"
    assert weights["field"] == "u128_decimal_strings"
    assert weights["input_shape"] == [4, 4]
    assert weights["conv"]["kernel_shape"] == [3, 3]
    assert weights["conv"]["filter_flat"] == ["1", "0", "1", "2", "0", "2", "1", "0", "1"]
    assert weights["pool"] == {"kernel": 2, "stride": 2, "mode": "sum"}
    assert weights["fc"]["weights_in_out"] == [["2", "3"]]
    assert weights["fc"]["bias"] == ["5", "7"]
    assert weights["weights_flat"] == [
        "1",
        "0",
        "1",
        "2",
        "0",
        "2",
        "1",
        "0",
        "1",
        "2",
        "3",
        "5",
        "7",
    ]
    assert weights["num_weights"] == 13


def test_conv_trace_matches_hand_computed_3x3_valid_mac() -> None:
    conv = _load("conv_trace.json")

    expected_windows = [
        ["1", "2", "3", "5", "6", "7", "9", "10", "11"],
        ["2", "3", "4", "6", "7", "8", "10", "11", "12"],
        ["5", "6", "7", "9", "10", "11", "13", "14", "15"],
        ["6", "7", "8", "10", "11", "12", "14", "15", "16"],
    ]
    filter_flat = [1, 0, 1, 2, 0, 2, 1, 0, 1]

    assert conv["input_shape"] == [4, 4]
    assert conv["output_shape"] == [2, 2]
    assert conv["input_flat"] == [str(value) for value in range(1, 17)]
    assert conv["filter_flat"] == [str(value) for value in filter_flat]
    assert conv["windows"] == expected_windows

    # Hand MACs:
    # [1,2,3;5,6,7;9,10,11] -> 1+3+10+14+9+11 = 48
    # [2,3,4;6,7,8;10,11,12] -> 2+4+12+16+10+12 = 56
    # [5,6,7;9,10,11;13,14,15] -> 5+7+18+22+13+15 = 80
    # [6,7,8;10,11,12;14,15,16] -> 6+8+20+24+14+16 = 88
    assert conv["output_flat"] == ["48", "56", "80", "88"]
    assert [
        sum(weight * value for weight, value in zip(filter_flat, _ints(window)))
        for window in conv["windows"]
    ] == [48, 56, 80, 88]


def test_pool_trace_matches_hand_computed_2x2_sum() -> None:
    pool = _load("pool_trace.json")

    assert pool["kernel"] == 2
    assert pool["stride"] == 2
    assert pool["mode"] == "sum"
    assert pool["windows"] == [["48", "56", "80", "88"]]
    assert pool["output_shape"] == [1, 1]
    assert pool["output_flat"] == ["272"]
    assert sum(_ints(pool["windows"][0])) == 272


def test_fc_trace_matches_hand_computed_one_to_two_with_bias() -> None:
    fc = _load("fc_trace.json")
    assert len(fc["layers"]) == 1
    layer = fc["layers"][0]

    assert layer["inputs"] == ["272"]
    assert layer["weights_in_out"] == [["2", "3"]]
    assert layer["bias"] == ["5", "7"]

    # y0 = 272*2 + 5 = 549; y1 = 272*3 + 7 = 823.
    assert layer["outputs"] == ["549", "823"]
    x = int(layer["inputs"][0])
    weights = _ints(layer["weights_in_out"][0])
    bias = _ints(layer["bias"])
    assert [x * weights[idx] + bias[idx] for idx in range(2)] == [549, 823]
