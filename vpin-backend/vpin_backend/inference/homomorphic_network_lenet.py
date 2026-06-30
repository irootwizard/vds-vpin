"""Homomorphic LeNet inference — multi-channel conv + 3 FC layers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.codec import real_to_fixed_point
from vpin_backend.inference.homomorphic_network_a import (
    encrypt_bias,
    fc_layer,
    flatten_ciphertext,
    my_conv2d,
)


@dataclass
class LeNetWeights:
    weight_conv1: np.ndarray  # (out_ch, in_ch, kH, kW)
    bias_conv1: np.ndarray    # (out_ch,)
    weight_conv2: np.ndarray  # (out_ch, in_ch, kH, kW)
    bias_conv2: np.ndarray    # (out_ch,)
    weight_c3: np.ndarray     # (400, 120)
    bias_c3: np.ndarray       # (120,)
    weight_fc4: np.ndarray    # (120, 84)
    bias_fc4: np.ndarray      # (84,)
    weight_fc5: np.ndarray    # (84, 10)
    bias_fc5: np.ndarray      # (10,)
    variant: str = "mnist"


def load_lenet_weights(weights_dir: Path, variant: str | None = None) -> LeNetWeights:
    d = Path(weights_dir)
    # Auto-detect by input channel count in conv1 filename
    if variant is None:
        variant = "cifar" if (d / "conv1_weight_6_3_5_5.npy").is_file() else "mnist"

    if variant == "mnist":
        return LeNetWeights(
            weight_conv1=np.load(d / "conv1_weight_6_1_5_5.npy"),
            bias_conv1=np.load(d / "conv1_bias_6.npy"),
            weight_conv2=np.load(d / "conv2_weight_16_6_5_5.npy"),
            bias_conv2=np.load(d / "conv2_bias_16.npy"),
            weight_c3=np.load(d / "c3_weight_400_120.npy"),
            bias_c3=np.load(d / "c3_bias_120.npy"),
            weight_fc4=np.load(d / "fc4_weight_120_84.npy"),
            bias_fc4=np.load(d / "fc4_bias_84.npy"),
            weight_fc5=np.load(d / "fc5_weight_84_10.npy"),
            bias_fc5=np.load(d / "fc5_bias_10.npy"),
            variant="mnist",
        )
    else:  # cifar — same naming convention as mnist, 3-channel conv1
        return LeNetWeights(
            weight_conv1=np.load(d / "conv1_weight_6_3_5_5.npy"),
            bias_conv1=np.load(d / "conv1_bias_6.npy"),
            weight_conv2=np.load(d / "conv2_weight_16_6_5_5.npy"),
            bias_conv2=np.load(d / "conv2_bias_16.npy"),
            weight_c3=np.load(d / "c3_weight_400_120.npy"),
            bias_c3=np.load(d / "c3_bias_120.npy"),
            weight_fc4=np.load(d / "fc4_weight_120_84.npy"),
            bias_fc4=np.load(d / "fc4_bias_84.npy"),
            weight_fc5=np.load(d / "fc5_weight_84_10.npy"),
            bias_fc5=np.load(d / "fc5_bias_10.npy"),
            variant="cifar",
        )


def lenet_conv_ciphertext(
    c1_in: np.ndarray,
    c2_in: np.ndarray,
    weights: np.ndarray,    # (out_ch, in_ch, kH, kW) — plaintext float
    bias_c1: np.ndarray,    # (out_ch,) encrypted bias EC points
    bias_c2: np.ndarray,
    identity: Point,
) -> tuple[np.ndarray, np.ndarray]:
    """Multi-channel homomorphic conv2d (no padding, stride 1)."""
    batch, in_ch, H, W = c1_in.shape
    out_ch, _, kH, kW = weights.shape
    out_H = H - kH + 1
    out_W = W - kW + 1
    weights_fp = real_to_fixed_point(weights.astype(np.float64), bits=16)

    c1_out = np.empty((batch, out_ch, out_H, out_W), dtype=object)
    c2_out = np.empty((batch, out_ch, out_H, out_W), dtype=object)

    for b in range(batch):
        for o in range(out_ch):
            acc_c1: np.ndarray | None = None
            acc_c2: np.ndarray | None = None
            for i in range(in_ch):
                ch_c1 = my_conv2d(c1_in[b, i], weights_fp[o, i], identity)
                ch_c2 = my_conv2d(c2_in[b, i], weights_fp[o, i], identity)
                if acc_c1 is None:
                    acc_c1 = ch_c1
                    acc_c2 = ch_c2
                else:
                    acc_c1 = acc_c1 + ch_c1
                    acc_c2 = acc_c2 + ch_c2
            for y in range(out_H):
                for x in range(out_W):
                    c1_out[b, o, y, x] = acc_c1[y, x] + bias_c1[o]
                    c2_out[b, o, y, x] = acc_c2[y, x] + bias_c2[o]

    return c1_out, c2_out


def lenet_fc_layer(
    c1_in: np.ndarray,
    c2_in: np.ndarray,
    weight: np.ndarray,   # (in_features, out_features) float
    bias: np.ndarray,     # (out_features,) float
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    bias_c1, bias_c2 = encrypt_bias(
        bias, generator=generator, public_key=public_key, curve_order=curve_order
    )
    return fc_layer(c1_in, c2_in, weight, bias_c1, bias_c2)
