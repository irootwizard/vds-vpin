"""Generate frozen Phase Z toy network trace vectors.

Toy network:
- 4x4 u128 input
- 3x3 single-channel valid convolution -> 2x2
- 2x2 sum pool -> one scalar
- FC 1 -> 2 with bias
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "toy"

INPUT_4X4 = [
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, 10, 11, 12],
    [13, 14, 15, 16],
]

CONV_FILTER_3X3 = [
    [1, 0, 1],
    [2, 0, 2],
    [1, 0, 1],
]

FC_WEIGHTS_IN_OUT = [[2, 3]]
FC_BIAS = [5, 7]


def _flatten(rows: Iterable[Iterable[int]]) -> list[int]:
    return [value for row in rows for value in row]


def _as_u128_strings(values: Iterable[int]) -> list[str]:
    return [str(value) for value in values]


def _valid_conv_windows(input_4x4: list[list[int]]) -> list[list[int]]:
    windows: list[list[int]] = []
    for row in range(2):
        for col in range(2):
            window = [input_4x4[row + dy][col + dx] for dy in range(3) for dx in range(3)]
            windows.append(window)
    return windows


def _dot(left: Iterable[int], right: Iterable[int]) -> int:
    return sum(a * b for a, b in zip(left, right))


def build_toy_vectors() -> dict[str, object]:
    conv_filter_flat = _flatten(CONV_FILTER_3X3)
    conv_windows = _valid_conv_windows(INPUT_4X4)
    conv_output = [_dot(conv_filter_flat, window) for window in conv_windows]

    pool_window = conv_output
    pool_output = [sum(pool_window)]

    fc_input = pool_output
    fc_outputs = [
        fc_input[0] * FC_WEIGHTS_IN_OUT[0][out_idx] + FC_BIAS[out_idx]
        for out_idx in range(2)
    ]

    weights = {
        "network": "phase_z_toy",
        "field": "u128_decimal_strings",
        "input_shape": [4, 4],
        "conv": {
            "in_channels": 1,
            "out_channels": 1,
            "kernel_shape": [3, 3],
            "stride": 1,
            "padding": 0,
            "filter_flat": _as_u128_strings(conv_filter_flat),
        },
        "pool": {
            "kernel": 2,
            "stride": 2,
            "mode": "sum",
        },
        "fc": {
            "inputs": 1,
            "outputs": 2,
            "weights_in_out": [
                _as_u128_strings(row) for row in FC_WEIGHTS_IN_OUT
            ],
            "bias": _as_u128_strings(FC_BIAS),
        },
        "weights_flat": _as_u128_strings(conv_filter_flat + _flatten(FC_WEIGHTS_IN_OUT) + FC_BIAS),
        "num_weights": len(conv_filter_flat) + len(_flatten(FC_WEIGHTS_IN_OUT)) + len(FC_BIAS),
    }

    conv_trace = {
        "input_shape": [4, 4],
        "input_flat": _as_u128_strings(_flatten(INPUT_4X4)),
        "filter_flat": _as_u128_strings(conv_filter_flat),
        "windows": [_as_u128_strings(window) for window in conv_windows],
        "output_shape": [2, 2],
        "output_flat": _as_u128_strings(conv_output),
    }

    pool_trace = {
        "kernel": 2,
        "stride": 2,
        "mode": "sum",
        "windows": [_as_u128_strings(pool_window)],
        "output_shape": [1, 1],
        "output_flat": _as_u128_strings(pool_output),
    }

    fc_trace = {
        "layers": [
            {
                "inputs": _as_u128_strings(fc_input),
                "weights_in_out": [
                    _as_u128_strings(row) for row in FC_WEIGHTS_IN_OUT
                ],
                "bias": _as_u128_strings(FC_BIAS),
                "outputs": _as_u128_strings(fc_outputs),
            }
        ]
    }

    return {
        "toy_full_weights.json": weights,
        "conv_trace.json": conv_trace,
        "pool_trace.json": pool_trace,
        "fc_trace.json": fc_trace,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, payload in build_toy_vectors().items():
        (OUT_DIR / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
