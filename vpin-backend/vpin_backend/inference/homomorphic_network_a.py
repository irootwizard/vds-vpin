"""
Homomorphic Network A — port of src/cnn_networks/Server.py without socket / rLCL / rLCR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.config import get_settings
from vpin_backend.crypto.ahe.codec import encrypt_scalar, real_to_fixed_point

CONV_FILTER = np.array([[1, 0, 1], [2, 0, 2], [1, 0, 1]], dtype=np.int64)

_op_counters = {"pt_mult": 0, "pt_add": 0}


def reset_op_counters() -> None:
    _op_counters["pt_mult"] = 0
    _op_counters["pt_add"] = 0


def get_op_counters() -> tuple[int, int]:
    return _op_counters["pt_add"], _op_counters["pt_mult"]


def _track_mult() -> None:
    _op_counters["pt_mult"] += 1


def _track_add() -> None:
    _op_counters["pt_add"] += 1


@dataclass
class NetworkAWeights:
    weight_fc1: np.ndarray
    bias_fc1: np.ndarray
    weight_fc2: np.ndarray
    bias_fc2: np.ndarray


def load_network_a_weights(weights_dir: Path | None = None) -> NetworkAWeights:
    root = weights_dir or (get_settings().cnn_networks_dir / "Pre_trained_model")
    return NetworkAWeights(
        weight_fc1=np.load(root / "weight_fc1_64_16.npy"),
        bias_fc1=np.load(root / "bias_fc1_16.npy"),
        weight_fc2=np.load(root / "weight_fc2_16_10.npy"),
        bias_fc2=np.load(root / "bias_fc2_10.npy"),
    )


def my_conv2d(
    input_data: np.ndarray,
    filter_weights: np.ndarray,
    identity_point: Point,
    *,
    padding_size: int = 0,
    stride: int = 1,
    ciphertext: bool = True,
) -> np.ndarray:
    input_height, input_width = input_data.shape
    filter_height, filter_width = filter_weights.shape

    if ciphertext:
        padded = np.pad(
            input_data,
            padding_size,
            mode="constant",
            constant_values=identity_point,
        )
    else:
        padded = np.pad(input_data, padding_size, mode="constant")

    output_height = (input_height + 2 * padding_size - filter_height) // stride + 1
    output_width = (input_width + 2 * padding_size - filter_width) // stride + 1

    if ciphertext:
        output_data = np.empty((output_height, output_width), dtype=object)
        for i in range(output_height):
            for j in range(output_width):
                window = padded[
                    i * stride : i * stride + filter_height,
                    j * stride : j * stride + filter_width,
                ]
                sum_value = None
                for ii in range(filter_height):
                    for jj in range(filter_width):
                        term = window[ii, jj] * filter_weights[ii, jj]
                        _track_mult()
                        if sum_value is None:
                            sum_value = term
                        else:
                            sum_value = sum_value + term
                            _track_add()
                output_data[i, j] = sum_value
        return output_data

    output_data = np.zeros((output_height, output_width))
    for i in range(output_height):
        for j in range(output_width):
            output_data[i, j] = np.sum(
                padded[i * stride : i * stride + filter_height, j * stride : j * stride + filter_width]
                * filter_weights
            )
    return output_data


def call_conv2_ciphertext(
    images_c1: np.ndarray,
    images_c2: np.ndarray,
    identity_point: Point,
) -> tuple[np.ndarray, np.ndarray]:
    batch, channels, height, width = images_c1.shape
    out_c1 = np.empty((batch, channels, height, width), dtype=object)
    out_c2 = np.empty((batch, channels, height, width), dtype=object)
    for i in range(batch):
        for j in range(channels):
            out_c1[i, j] = my_conv2d(
                images_c1[i, j],
                CONV_FILTER,
                identity_point,
                padding_size=1,
                stride=1,
                ciphertext=True,
            )
            out_c2[i, j] = my_conv2d(
                images_c2[i, j],
                CONV_FILTER,
                identity_point,
                padding_size=1,
                stride=1,
                ciphertext=True,
            )
    return out_c1, out_c2


def my_avg_pool2d(
    input_data: np.ndarray,
    identity_point: Point,
    kernel_size: int,
    stride: int,
) -> np.ndarray:
    input_height, input_width = input_data.shape
    output_height = (input_height - kernel_size) // stride + 1
    output_width = (input_width - kernel_size) // stride + 1
    output_data = np.empty((output_height, output_width), dtype=object)
    inv_fp = int(real_to_fixed_point(np.array([1.0 / (kernel_size**2)]), bits=10)[0])

    for i in range(output_height):
        for j in range(output_width):
            sum_value = None
            for ii in range(kernel_size):
                for jj in range(kernel_size):
                    cell = input_data[i * stride + ii, j * stride + jj]
                    if cell == 0:
                        cell = identity_point
                    if sum_value is None:
                        sum_value = cell
                    else:
                        sum_value = sum_value + cell
                        _track_add()
            output_data[i, j] = sum_value * inv_fp
            _track_mult()
    return output_data


def call_avg_pool2d_ciphertext(
    image_c1: np.ndarray,
    image_c2: np.ndarray,
    identity_point: Point,
    kernel_size: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    batch, channels, _, _ = image_c1.shape
    output_height = image_c1.shape[2] // kernel_size
    output_width = image_c1.shape[3] // kernel_size
    out_c1 = np.empty((batch, channels, output_height, output_width), dtype=object)
    out_c2 = np.empty((batch, channels, output_height, output_width), dtype=object)
    for i in range(batch):
        for j in range(channels):
            out_c1[i, j] = my_avg_pool2d(image_c1[i, j], identity_point, kernel_size, stride)
            out_c2[i, j] = my_avg_pool2d(image_c2[i, j], identity_point, kernel_size, stride)
    return out_c1, out_c2


def flatten_ciphertext(x_c1: np.ndarray, x_c2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    input_size = x_c1.shape[1] * x_c1.shape[2] * x_c1.shape[3]
    return x_c1.reshape(1, input_size), x_c2.reshape(1, input_size)


def encrypt_bias(
    bias: np.ndarray,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    fixed = real_to_fixed_point(bias.astype(np.float64), bits=16)
    c1 = np.empty(fixed.shape[0], dtype=object)
    c2 = np.empty(fixed.shape[0], dtype=object)
    for i in range(fixed.shape[0]):
        c1[i], c2[i] = encrypt_scalar(
            int(fixed[i]),
            generator=generator,
            public_key=public_key,
            curve_order=curve_order,
        )
    return c1, c2


def fc_layer(
    input_c1: np.ndarray,
    input_c2: np.ndarray,
    weight_matrix: np.ndarray,
    bias_c1: np.ndarray,
    bias_c2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    weight_fp = real_to_fixed_point(weight_matrix.astype(np.float64), bits=16)
    mat_c1 = np.matmul(input_c1, weight_fp)
    mat_c2 = np.matmul(input_c2, weight_fp)
    out_c1 = np.empty((1, weight_fp.shape[1]), dtype=object)
    out_c2 = np.empty((1, weight_fp.shape[1]), dtype=object)
    for j in range(weight_fp.shape[1]):
        out_c1[0, j] = mat_c1[0, j] + bias_c1[j]
        out_c2[0, j] = mat_c2[0, j] + bias_c2[j]
        _track_add()
    return out_c1, out_c2


def conv2_ciphertext(
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    identity_point: Point,
) -> tuple[np.ndarray, np.ndarray]:
    return call_conv2_ciphertext(enc_c1, enc_c2, identity_point)


def avg_pool_ciphertext(
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    identity_point: Point,
    kernel_size: int = 4,
    stride: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    return call_avg_pool2d_ciphertext(enc_c1, enc_c2, identity_point, kernel_size, stride)


def fc1_layer(
    weights: NetworkAWeights,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    bias_c1, bias_c2 = encrypt_bias(
        weights.bias_fc1,
        generator=generator,
        public_key=public_key,
        curve_order=curve_order,
    )
    return fc_layer(enc_c1, enc_c2, weights.weight_fc1, bias_c1, bias_c2)


def fc2_layer(
    weights: NetworkAWeights,
    enc_c1: np.ndarray,
    enc_c2: np.ndarray,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    bias_c1, bias_c2 = encrypt_bias(
        weights.bias_fc2,
        generator=generator,
        public_key=public_key,
        curve_order=curve_order,
    )
    return fc_layer(enc_c1, enc_c2, weights.weight_fc2, bias_c1, bias_c2)
