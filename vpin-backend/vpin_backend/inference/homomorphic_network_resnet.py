"""Homomorphic ResNet18 inference — BN-folded conv layers + residual shortcuts.

Fixed-point protocol:
  - Input to each block: f=16 (re-encrypted after client relu_then_shift)
  - Conv output (f=32): client decrypts, ReLU, shift 32→16, re-encrypts
  - Identity shortcut: server multiplies block-input ciphertext by 2^16 to
    align f=16 → f=32, then adds to conv2 output (f=32)
  - Downsample shortcut: server runs 1×1 ds_conv (folded) on block input
    (f=16→f=32), holds the ciphertext, adds to conv2 output (both f=32)
  - Final: AvgPool(4×4) + Linear(512→10) merged on server (both linear)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.codec import real_to_fixed_point
from vpin_backend.inference.homomorphic_network_a import (
    encrypt_bias,
    fc_layer,
    flatten_ciphertext,
    my_avg_pool2d,
    my_conv2d,
)

_SCALE_16 = 1 << 16  # 2^16 — used to align identity shortcut f=16 → f=32


@dataclass
class ResNetWeights:
    # Stem: conv1(3→64, 3×3, p=1) + BN fold
    stem_w: np.ndarray   # (64, 3, 3, 3)
    stem_b: np.ndarray   # (64,)

    # Layer1 block0 (identity shortcut, 64→64)
    l1b0_conv1_w: np.ndarray  # (64, 64, 3, 3)
    l1b0_conv1_b: np.ndarray  # (64,)
    l1b0_conv2_w: np.ndarray  # (64, 64, 3, 3)
    l1b0_conv2_b: np.ndarray  # (64,)

    # Layer1 block1 (identity shortcut, 64→64)
    l1b1_conv1_w: np.ndarray
    l1b1_conv1_b: np.ndarray
    l1b1_conv2_w: np.ndarray
    l1b1_conv2_b: np.ndarray

    # Layer2 block0 (downsample shortcut, 64→128, stride=2)
    l2b0_conv1_w: np.ndarray  # (128, 64, 3, 3)
    l2b0_conv1_b: np.ndarray  # (128,)
    l2b0_conv2_w: np.ndarray  # (128, 128, 3, 3)
    l2b0_conv2_b: np.ndarray  # (128,)
    l2b0_ds_w: np.ndarray     # (128, 64, 1, 1)
    l2b0_ds_b: np.ndarray     # (128,)

    # Layer2 block1 (identity shortcut, 128→128)
    l2b1_conv1_w: np.ndarray
    l2b1_conv1_b: np.ndarray
    l2b1_conv2_w: np.ndarray
    l2b1_conv2_b: np.ndarray

    # Layer3 block0 (downsample shortcut, 128→256, stride=2)
    l3b0_conv1_w: np.ndarray
    l3b0_conv1_b: np.ndarray
    l3b0_conv2_w: np.ndarray
    l3b0_conv2_b: np.ndarray
    l3b0_ds_w: np.ndarray
    l3b0_ds_b: np.ndarray

    # Layer3 block1 (identity shortcut, 256→256)
    l3b1_conv1_w: np.ndarray
    l3b1_conv1_b: np.ndarray
    l3b1_conv2_w: np.ndarray
    l3b1_conv2_b: np.ndarray

    # Layer4 block0 (downsample shortcut, 256→512, stride=2)
    l4b0_conv1_w: np.ndarray
    l4b0_conv1_b: np.ndarray
    l4b0_conv2_w: np.ndarray
    l4b0_conv2_b: np.ndarray
    l4b0_ds_w: np.ndarray
    l4b0_ds_b: np.ndarray

    # Layer4 block1 (identity shortcut, 512→512)
    l4b1_conv1_w: np.ndarray
    l4b1_conv1_b: np.ndarray
    l4b1_conv2_w: np.ndarray
    l4b1_conv2_b: np.ndarray

    # Final linear
    linear_w: np.ndarray  # (512, 10)
    linear_b: np.ndarray  # (10,)


def load_resnet_weights(weights_dir: Path) -> ResNetWeights:
    d = Path(weights_dir)

    def _w(name: str) -> np.ndarray:
        return np.load(d / name)

    return ResNetWeights(
        stem_w=_w("stem_weight_64_3_3_3.npy"),
        stem_b=_w("stem_bias_64.npy"),
        l1b0_conv1_w=_w("l1b0_conv1_weight_64_64_3_3.npy"),
        l1b0_conv1_b=_w("l1b0_conv1_bias_64.npy"),
        l1b0_conv2_w=_w("l1b0_conv2_weight_64_64_3_3.npy"),
        l1b0_conv2_b=_w("l1b0_conv2_bias_64.npy"),
        l1b1_conv1_w=_w("l1b1_conv1_weight_64_64_3_3.npy"),
        l1b1_conv1_b=_w("l1b1_conv1_bias_64.npy"),
        l1b1_conv2_w=_w("l1b1_conv2_weight_64_64_3_3.npy"),
        l1b1_conv2_b=_w("l1b1_conv2_bias_64.npy"),
        l2b0_conv1_w=_w("l2b0_conv1_weight_128_64_3_3.npy"),
        l2b0_conv1_b=_w("l2b0_conv1_bias_128.npy"),
        l2b0_conv2_w=_w("l2b0_conv2_weight_128_128_3_3.npy"),
        l2b0_conv2_b=_w("l2b0_conv2_bias_128.npy"),
        l2b0_ds_w=_w("l2b0_ds_weight_128_64_1_1.npy"),
        l2b0_ds_b=_w("l2b0_ds_bias_128.npy"),
        l2b1_conv1_w=_w("l2b1_conv1_weight_128_128_3_3.npy"),
        l2b1_conv1_b=_w("l2b1_conv1_bias_128.npy"),
        l2b1_conv2_w=_w("l2b1_conv2_weight_128_128_3_3.npy"),
        l2b1_conv2_b=_w("l2b1_conv2_bias_128.npy"),
        l3b0_conv1_w=_w("l3b0_conv1_weight_256_128_3_3.npy"),
        l3b0_conv1_b=_w("l3b0_conv1_bias_256.npy"),
        l3b0_conv2_w=_w("l3b0_conv2_weight_256_256_3_3.npy"),
        l3b0_conv2_b=_w("l3b0_conv2_bias_256.npy"),
        l3b0_ds_w=_w("l3b0_ds_weight_256_128_1_1.npy"),
        l3b0_ds_b=_w("l3b0_ds_bias_256.npy"),
        l3b1_conv1_w=_w("l3b1_conv1_weight_256_256_3_3.npy"),
        l3b1_conv1_b=_w("l3b1_conv1_bias_256.npy"),
        l3b1_conv2_w=_w("l3b1_conv2_weight_256_256_3_3.npy"),
        l3b1_conv2_b=_w("l3b1_conv2_bias_256.npy"),
        l4b0_conv1_w=_w("l4b0_conv1_weight_512_256_3_3.npy"),
        l4b0_conv1_b=_w("l4b0_conv1_bias_512.npy"),
        l4b0_conv2_w=_w("l4b0_conv2_weight_512_512_3_3.npy"),
        l4b0_conv2_b=_w("l4b0_conv2_bias_512.npy"),
        l4b0_ds_w=_w("l4b0_ds_weight_512_256_1_1.npy"),
        l4b0_ds_b=_w("l4b0_ds_bias_512.npy"),
        l4b1_conv1_w=_w("l4b1_conv1_weight_512_512_3_3.npy"),
        l4b1_conv1_b=_w("l4b1_conv1_bias_512.npy"),
        l4b1_conv2_w=_w("l4b1_conv2_weight_512_512_3_3.npy"),
        l4b1_conv2_b=_w("l4b1_conv2_bias_512.npy"),
        linear_w=_w("linear_weight_512_10.npy"),
        linear_b=_w("linear_bias_10.npy"),
    )


# ---------------------------------------------------------------------------
# Homomorphic conv (multi-channel, configurable padding / stride)
# ---------------------------------------------------------------------------

def resnet_conv_ciphertext(
    c1_in: np.ndarray,    # (batch, in_ch, H, W) EC points
    c2_in: np.ndarray,
    weights: np.ndarray,  # (out_ch, in_ch, kH, kW) float64
    bias_c1: np.ndarray,  # (out_ch,) encrypted EC points
    bias_c2: np.ndarray,
    identity: Point,
    *,
    padding: int = 1,
    stride: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    batch, in_ch, H, W = c1_in.shape
    out_ch, _, kH, kW = weights.shape
    H2 = (H + 2 * padding - kH) // stride + 1
    W2 = (W + 2 * padding - kW) // stride + 1
    weights_fp = real_to_fixed_point(weights.astype(np.float64), bits=16)

    c1_out = np.empty((batch, out_ch, H2, W2), dtype=object)
    c2_out = np.empty((batch, out_ch, H2, W2), dtype=object)

    for b in range(batch):
        for o in range(out_ch):
            acc_c1: np.ndarray | None = None
            acc_c2: np.ndarray | None = None
            for i in range(in_ch):
                ch_c1 = my_conv2d(
                    c1_in[b, i], weights_fp[o, i], identity,
                    padding_size=padding, stride=stride,
                )
                ch_c2 = my_conv2d(
                    c2_in[b, i], weights_fp[o, i], identity,
                    padding_size=padding, stride=stride,
                )
                if acc_c1 is None:
                    acc_c1 = ch_c1
                    acc_c2 = ch_c2
                else:
                    acc_c1 = acc_c1 + ch_c1
                    acc_c2 = acc_c2 + ch_c2
            for y in range(H2):
                for x in range(W2):
                    c1_out[b, o, y, x] = acc_c1[y, x] + bias_c1[o]
                    c2_out[b, o, y, x] = acc_c2[y, x] + bias_c2[o]

    return c1_out, c2_out


# ---------------------------------------------------------------------------
# Residual shortcut additions
# ---------------------------------------------------------------------------

def resnet_add_identity_shortcut(
    c1_main: np.ndarray,
    c2_main: np.ndarray,
    c1_sc: np.ndarray,
    c2_sc: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Add identity shortcut: sc (f=16) × 2^16 → f=32, then add to main (f=32)."""
    c1_out = np.empty_like(c1_main)
    c2_out = np.empty_like(c2_main)
    for idx in np.ndindex(c1_main.shape):
        c1_out[idx] = c1_main[idx] + _SCALE_16 * c1_sc[idx]
        c2_out[idx] = c2_main[idx] + _SCALE_16 * c2_sc[idx]
    return c1_out, c2_out


def resnet_add_ds_shortcut(
    c1_main: np.ndarray,
    c2_main: np.ndarray,
    c1_ds: np.ndarray,
    c2_ds: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Add downsample shortcut: both already at f=32 (ds_conv output)."""
    c1_out = np.empty_like(c1_main)
    c2_out = np.empty_like(c2_main)
    for idx in np.ndindex(c1_main.shape):
        c1_out[idx] = c1_main[idx] + c1_ds[idx]
        c2_out[idx] = c2_main[idx] + c2_ds[idx]
    return c1_out, c2_out


# ---------------------------------------------------------------------------
# AvgPool(4×4) + Linear(512→10) merged — both linear, no intermediate round
# ---------------------------------------------------------------------------

def resnet_avgpool_fc(
    c1_in: np.ndarray,
    c2_in: np.ndarray,
    weights: ResNetWeights,
    identity: Point,
    *,
    generator: Point,
    public_key: Point,
    curve_order: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Global AvgPool(4×4) → flatten → Linear(512→10), all in one server step."""
    batch, C, H, W = c1_in.shape  # (1, 512, 4, 4)
    pool_out_c1 = np.empty((batch, C, 1, 1), dtype=object)
    pool_out_c2 = np.empty((batch, C, 1, 1), dtype=object)
    for b in range(batch):
        for c in range(C):
            pool_out_c1[b, c, 0, 0] = my_avg_pool2d(c1_in[b, c], identity, H, H)[0, 0]
            pool_out_c2[b, c, 0, 0] = my_avg_pool2d(c2_in[b, c], identity, H, H)[0, 0]

    flat_c1, flat_c2 = flatten_ciphertext(pool_out_c1, pool_out_c2)

    bias_c1, bias_c2 = encrypt_bias(
        weights.linear_b,
        generator=generator,
        public_key=public_key,
        curve_order=curve_order,
    )
    return fc_layer(flat_c1, flat_c2, weights.linear_w, bias_c1, bias_c2)
