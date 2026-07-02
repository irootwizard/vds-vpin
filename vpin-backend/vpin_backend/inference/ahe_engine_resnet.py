"""AHE inference engine for ResNet18/CIFAR-10 — 17-phase protocol.

Phase sequence (17 × relu_then_shift + 1 logits_only):
  initial          → after_stem
  after_stem       → after_l1b0c1
  after_l1b0c1     → after_l1b0c2   (server adds identity shortcut to conv2 out)
  after_l1b0c2     → after_l1b1c1
  after_l1b1c1     → after_l1b1c2   (identity shortcut)
  after_l1b1c2     → after_l2b0c1
  after_l2b0c1     → after_l2b0c2   (server adds downsample shortcut; shortcut was
                                       computed on the block0 input held from after_l1b1c2)
  after_l2b0c2     → after_l2b1c1
  after_l2b1c1     → after_l2b1c2   (identity shortcut)
  after_l2b1c2     → after_l3b0c1
  after_l3b0c1     → after_l3b0c2   (downsample)
  after_l3b0c2     → after_l3b1c1
  after_l3b1c1     → after_l3b1c2   (identity)
  after_l3b1c2     → after_l4b0c1
  after_l4b0c1     → after_l4b0c2   (downsample)
  after_l4b0c2     → after_l4b1c1
  after_l4b1c1     → after_l4b1c2   (identity)
  after_l4b1c2     → after_pool_linear  (AvgPool+Linear merged, logits_only)

Downsample shortcut timing:
  When the client sends after_l{N}b1c2 (block1 output, which is the input to
  block0 of the next layer), the server saves this ciphertext as the pending
  downsample shortcut input, then computes ds_conv on it immediately and holds
  the result. When conv2 of block0 finishes (after_l{N+1}b0c1 returned and
  client re-encrypts), the server adds the ds shortcut to conv2.

  Actually, the shortcut is the *block0 input*, which the client sends as the
  re-encrypted ciphertext after the PREVIOUS relu_then_shift. So:
    - Client sends after_l1b1c2 (= block0 of layer2 input, f=16)
    - Server immediately computes ds_conv on it → holds c1_ds, c2_ds at f=32
    - Server runs conv1 → sends back after_l2b0c1 for client relu_then_shift
    - Client sends after_l2b0c1 (f=16)
    - Server runs conv2 → gets conv2_out (f=32)
    - Server adds c1_ds + conv2_out → sends back after_l2b0c2
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.inference.ahe_engine import EngineStepResult, TruncateStep
from vpin_backend.inference.homomorphic_network_a import encrypt_bias
from vpin_backend.inference.homomorphic_network_resnet import (
    ResNetWeights,
    resnet_add_ds_shortcut,
    resnet_add_identity_shortcut,
    resnet_avgpool_fc,
    resnet_conv_ciphertext,
)


class ResNetPhase(str, Enum):
    WAIT_INITIAL      = "wait_initial"
    WAIT_AFTER_STEM   = "wait_after_stem"
    WAIT_AFTER_L1B0C1 = "wait_after_l1b0c1"
    WAIT_AFTER_L1B0C2 = "wait_after_l1b0c2"
    WAIT_AFTER_L1B1C1 = "wait_after_l1b1c1"
    WAIT_AFTER_L1B1C2 = "wait_after_l1b1c2"
    WAIT_AFTER_L2B0C1 = "wait_after_l2b0c1"
    WAIT_AFTER_L2B0C2 = "wait_after_l2b0c2"
    WAIT_AFTER_L2B1C1 = "wait_after_l2b1c1"
    WAIT_AFTER_L2B1C2 = "wait_after_l2b1c2"
    WAIT_AFTER_L3B0C1 = "wait_after_l3b0c1"
    WAIT_AFTER_L3B0C2 = "wait_after_l3b0c2"
    WAIT_AFTER_L3B1C1 = "wait_after_l3b1c1"
    WAIT_AFTER_L3B1C2 = "wait_after_l3b1c2"
    WAIT_AFTER_L4B0C1 = "wait_after_l4b0c1"
    WAIT_AFTER_L4B0C2 = "wait_after_l4b0c2"
    WAIT_AFTER_L4B1C1 = "wait_after_l4b1c1"
    WAIT_AFTER_L4B1C2 = "wait_after_l4b1c2"
    DONE              = "done"


def _step(phase_id: str, action: str, shift: int | None, shape: list[int]) -> TruncateStep:
    return TruncateStep(phase_id=phase_id, client_action=action, shift_bits=shift, shape=shape)


class AheResnetEngine:
    def __init__(
        self,
        *,
        public_key: Point,
        weights: ResNetWeights,
    ) -> None:
        _, _, order, generator, identity = curve_e2_info()
        self.public_key = public_key
        self.weights = weights
        self.phase = ResNetPhase.WAIT_INITIAL
        self._order = order
        self._generator = generator
        self._identity = identity
        # Pending downsample shortcut ciphertext (computed before conv1, added after conv2)
        self._ds_c1: np.ndarray | None = None
        self._ds_c2: np.ndarray | None = None
        # Pending identity shortcut (the block-input re-encrypted by client)
        self._id_c1: np.ndarray | None = None
        self._id_c2: np.ndarray | None = None

    @classmethod
    def for_network(
        cls,
        *,
        public_key: Point,
        weights: ResNetWeights,
        network_id: str,
    ) -> AheResnetEngine:
        return cls(public_key=public_key, weights=weights)

    def _ebias(self, bias: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return encrypt_bias(
            bias,
            generator=self._generator,
            public_key=self.public_key,
            curve_order=self._order,
        )

    def _conv(
        self,
        c1: np.ndarray,
        c2: np.ndarray,
        w: np.ndarray,
        b: np.ndarray,
        *,
        padding: int = 1,
        stride: int = 1,
    ) -> tuple[np.ndarray, np.ndarray]:
        bc1, bc2 = self._ebias(b)
        return resnet_conv_ciphertext(c1, c2, w, bc1, bc2, self._identity,
                                      padding=padding, stride=stride)

    # ------------------------------------------------------------------
    def bind_initial_ciphertext(self, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        if self.phase != ResNetPhase.WAIT_INITIAL:
            raise ValueError(f"unexpected phase {self.phase}")
        oc1, oc2 = self._conv(c1, c2, self.weights.stem_w, self.weights.stem_b)
        self.phase = ResNetPhase.WAIT_AFTER_STEM
        return EngineStepResult(
            truncate=_step("after_stem", "relu_then_shift", 32, list(oc1.shape)),
            output_c1=oc1, output_c2=oc2,
        )

    # ------------------------------------------------------------------
    def accept_client_ciphertext(
        self, phase_id: str, c1: np.ndarray, c2: np.ndarray
    ) -> EngineStepResult:
        wt = self.weights

        # ── Layer1 Block0 ──────────────────────────────────────────────
        if phase_id == "after_stem" and self.phase == ResNetPhase.WAIT_AFTER_STEM:
            # Save block0 input for identity shortcut (used after conv2)
            self._id_c1, self._id_c2 = c1, c2
            oc1, oc2 = self._conv(c1, c2, wt.l1b0_conv1_w, wt.l1b0_conv1_b)
            self.phase = ResNetPhase.WAIT_AFTER_L1B0C1
            return EngineStepResult(
                truncate=_step("after_l1b0c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l1b0c1" and self.phase == ResNetPhase.WAIT_AFTER_L1B0C1:
            oc1, oc2 = self._conv(c1, c2, wt.l1b0_conv2_w, wt.l1b0_conv2_b)
            # Add identity shortcut (block input × 2^16 to align f=16→f=32)
            oc1, oc2 = resnet_add_identity_shortcut(oc1, oc2, self._id_c1, self._id_c2)
            self._id_c1 = self._id_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L1B0C2
            return EngineStepResult(
                truncate=_step("after_l1b0c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer1 Block1 ──────────────────────────────────────────────
        if phase_id == "after_l1b0c2" and self.phase == ResNetPhase.WAIT_AFTER_L1B0C2:
            self._id_c1, self._id_c2 = c1, c2
            oc1, oc2 = self._conv(c1, c2, wt.l1b1_conv1_w, wt.l1b1_conv1_b)
            self.phase = ResNetPhase.WAIT_AFTER_L1B1C1
            return EngineStepResult(
                truncate=_step("after_l1b1c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l1b1c1" and self.phase == ResNetPhase.WAIT_AFTER_L1B1C1:
            oc1, oc2 = self._conv(c1, c2, wt.l1b1_conv2_w, wt.l1b1_conv2_b)
            oc1, oc2 = resnet_add_identity_shortcut(oc1, oc2, self._id_c1, self._id_c2)
            self._id_c1 = self._id_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L1B1C2
            return EngineStepResult(
                truncate=_step("after_l1b1c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer2 Block0 (downsample, stride=2) ───────────────────────
        if phase_id == "after_l1b1c2" and self.phase == ResNetPhase.WAIT_AFTER_L1B1C2:
            # Compute downsample shortcut now (1×1 conv, stride=2, no padding)
            ds_bc1, ds_bc2 = self._ebias(wt.l2b0_ds_b)
            self._ds_c1, self._ds_c2 = resnet_conv_ciphertext(
                c1, c2, wt.l2b0_ds_w, ds_bc1, ds_bc2, self._identity,
                padding=0, stride=2,
            )
            # conv1 of block0 (stride=2)
            oc1, oc2 = self._conv(c1, c2, wt.l2b0_conv1_w, wt.l2b0_conv1_b, stride=2)
            self.phase = ResNetPhase.WAIT_AFTER_L2B0C1
            return EngineStepResult(
                truncate=_step("after_l2b0c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l2b0c1" and self.phase == ResNetPhase.WAIT_AFTER_L2B0C1:
            oc1, oc2 = self._conv(c1, c2, wt.l2b0_conv2_w, wt.l2b0_conv2_b)
            oc1, oc2 = resnet_add_ds_shortcut(oc1, oc2, self._ds_c1, self._ds_c2)
            self._ds_c1 = self._ds_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L2B0C2
            return EngineStepResult(
                truncate=_step("after_l2b0c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer2 Block1 ──────────────────────────────────────────────
        if phase_id == "after_l2b0c2" and self.phase == ResNetPhase.WAIT_AFTER_L2B0C2:
            self._id_c1, self._id_c2 = c1, c2
            oc1, oc2 = self._conv(c1, c2, wt.l2b1_conv1_w, wt.l2b1_conv1_b)
            self.phase = ResNetPhase.WAIT_AFTER_L2B1C1
            return EngineStepResult(
                truncate=_step("after_l2b1c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l2b1c1" and self.phase == ResNetPhase.WAIT_AFTER_L2B1C1:
            oc1, oc2 = self._conv(c1, c2, wt.l2b1_conv2_w, wt.l2b1_conv2_b)
            oc1, oc2 = resnet_add_identity_shortcut(oc1, oc2, self._id_c1, self._id_c2)
            self._id_c1 = self._id_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L2B1C2
            return EngineStepResult(
                truncate=_step("after_l2b1c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer3 Block0 (downsample, stride=2) ───────────────────────
        if phase_id == "after_l2b1c2" and self.phase == ResNetPhase.WAIT_AFTER_L2B1C2:
            ds_bc1, ds_bc2 = self._ebias(wt.l3b0_ds_b)
            self._ds_c1, self._ds_c2 = resnet_conv_ciphertext(
                c1, c2, wt.l3b0_ds_w, ds_bc1, ds_bc2, self._identity,
                padding=0, stride=2,
            )
            oc1, oc2 = self._conv(c1, c2, wt.l3b0_conv1_w, wt.l3b0_conv1_b, stride=2)
            self.phase = ResNetPhase.WAIT_AFTER_L3B0C1
            return EngineStepResult(
                truncate=_step("after_l3b0c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l3b0c1" and self.phase == ResNetPhase.WAIT_AFTER_L3B0C1:
            oc1, oc2 = self._conv(c1, c2, wt.l3b0_conv2_w, wt.l3b0_conv2_b)
            oc1, oc2 = resnet_add_ds_shortcut(oc1, oc2, self._ds_c1, self._ds_c2)
            self._ds_c1 = self._ds_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L3B0C2
            return EngineStepResult(
                truncate=_step("after_l3b0c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer3 Block1 ──────────────────────────────────────────────
        if phase_id == "after_l3b0c2" and self.phase == ResNetPhase.WAIT_AFTER_L3B0C2:
            self._id_c1, self._id_c2 = c1, c2
            oc1, oc2 = self._conv(c1, c2, wt.l3b1_conv1_w, wt.l3b1_conv1_b)
            self.phase = ResNetPhase.WAIT_AFTER_L3B1C1
            return EngineStepResult(
                truncate=_step("after_l3b1c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l3b1c1" and self.phase == ResNetPhase.WAIT_AFTER_L3B1C1:
            oc1, oc2 = self._conv(c1, c2, wt.l3b1_conv2_w, wt.l3b1_conv2_b)
            oc1, oc2 = resnet_add_identity_shortcut(oc1, oc2, self._id_c1, self._id_c2)
            self._id_c1 = self._id_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L3B1C2
            return EngineStepResult(
                truncate=_step("after_l3b1c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer4 Block0 (downsample, stride=2) ───────────────────────
        if phase_id == "after_l3b1c2" and self.phase == ResNetPhase.WAIT_AFTER_L3B1C2:
            ds_bc1, ds_bc2 = self._ebias(wt.l4b0_ds_b)
            self._ds_c1, self._ds_c2 = resnet_conv_ciphertext(
                c1, c2, wt.l4b0_ds_w, ds_bc1, ds_bc2, self._identity,
                padding=0, stride=2,
            )
            oc1, oc2 = self._conv(c1, c2, wt.l4b0_conv1_w, wt.l4b0_conv1_b, stride=2)
            self.phase = ResNetPhase.WAIT_AFTER_L4B0C1
            return EngineStepResult(
                truncate=_step("after_l4b0c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l4b0c1" and self.phase == ResNetPhase.WAIT_AFTER_L4B0C1:
            oc1, oc2 = self._conv(c1, c2, wt.l4b0_conv2_w, wt.l4b0_conv2_b)
            oc1, oc2 = resnet_add_ds_shortcut(oc1, oc2, self._ds_c1, self._ds_c2)
            self._ds_c1 = self._ds_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L4B0C2
            return EngineStepResult(
                truncate=_step("after_l4b0c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── Layer4 Block1 ──────────────────────────────────────────────
        if phase_id == "after_l4b0c2" and self.phase == ResNetPhase.WAIT_AFTER_L4B0C2:
            self._id_c1, self._id_c2 = c1, c2
            oc1, oc2 = self._conv(c1, c2, wt.l4b1_conv1_w, wt.l4b1_conv1_b)
            self.phase = ResNetPhase.WAIT_AFTER_L4B1C1
            return EngineStepResult(
                truncate=_step("after_l4b1c1", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        if phase_id == "after_l4b1c1" and self.phase == ResNetPhase.WAIT_AFTER_L4B1C1:
            oc1, oc2 = self._conv(c1, c2, wt.l4b1_conv2_w, wt.l4b1_conv2_b)
            oc1, oc2 = resnet_add_identity_shortcut(oc1, oc2, self._id_c1, self._id_c2)
            self._id_c1 = self._id_c2 = None
            self.phase = ResNetPhase.WAIT_AFTER_L4B1C2
            return EngineStepResult(
                truncate=_step("after_l4b1c2", "relu_then_shift", 32, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
            )

        # ── AvgPool + Linear → logits ──────────────────────────────────
        if phase_id == "after_l4b1c2" and self.phase == ResNetPhase.WAIT_AFTER_L4B1C2:
            oc1, oc2 = resnet_avgpool_fc(
                c1, c2, wt, self._identity,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._order,
            )
            self.phase = ResNetPhase.DONE
            return EngineStepResult(
                truncate=_step("after_pool_linear", "logits_only", None, list(oc1.shape)),
                output_c1=oc1, output_c2=oc2,
                inference_complete=True,
            )

        raise ValueError(f"unexpected phase_id={phase_id!r} in state {self.phase}")
