"""AHE inference engine for LeNet (MNIST / CIFAR) — 5-phase protocol."""
from __future__ import annotations

from enum import Enum

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.inference.ahe_engine import EngineStepResult, TruncateStep
from vpin_backend.inference.homomorphic_network_a import encrypt_bias, flatten_ciphertext
from vpin_backend.inference.homomorphic_network_lenet import (
    LeNetWeights,
    lenet_conv_ciphertext,
    lenet_fc_layer,
)


class LeNetPhase(str, Enum):
    WAIT_INITIAL = "wait_initial"
    WAIT_AFTER_CONV1 = "wait_after_conv1"
    WAIT_AFTER_CONV2 = "wait_after_conv2"
    WAIT_AFTER_C3 = "wait_after_c3"
    WAIT_AFTER_FC4 = "wait_after_fc4"
    DONE = "done"


class AheLenetEngine:
    def __init__(
        self,
        *,
        public_key: Point,
        weights: LeNetWeights,
        network_id: str = "lenet_mnist",
        skip_return_phases: list[str] | None = None,
    ) -> None:
        _, _, order, generator, identity = curve_e2_info()
        self.public_key = public_key
        self.weights = weights
        self.network_id = network_id
        self.skip_return_phases = skip_return_phases or []
        self.phase = LeNetPhase.WAIT_INITIAL
        self._order = order
        self._generator = generator
        self._identity = identity

    @classmethod
    def for_network(
        cls,
        *,
        public_key: Point,
        weights: LeNetWeights,
        network_id: str,
        skip_return_phases: list[str] | None = None,
    ) -> AheLenetEngine:
        return cls(
            public_key=public_key,
            weights=weights,
            network_id=network_id,
            skip_return_phases=skip_return_phases,
        )

    def _encrypt_bias(self, bias: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return encrypt_bias(
            bias,
            generator=self._generator,
            public_key=self.public_key,
            curve_order=self._order,
        )

    def bind_initial_ciphertext(self, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        if self.phase != LeNetPhase.WAIT_INITIAL:
            raise ValueError(f"unexpected phase {self.phase}")
        # Adapt channel count if input doesn't match conv1 expectations.
        # Allows testing CIFAR model with 1-channel MNIST gallery images.
        expected_in_ch = self.weights.weight_conv1.shape[1]
        actual_in_ch = c1.shape[1]
        if actual_in_ch != expected_in_ch:
            if actual_in_ch < expected_in_ch:
                repeats = (expected_in_ch + actual_in_ch - 1) // actual_in_ch
                c1 = np.concatenate([c1] * repeats, axis=1)[:, :expected_in_ch]
                c2 = np.concatenate([c2] * repeats, axis=1)[:, :expected_in_ch]
            else:
                c1 = c1[:, :expected_in_ch]
                c2 = c2[:, :expected_in_ch]
        bc1, bc2 = self._encrypt_bias(self.weights.bias_conv1)
        out_c1, out_c2 = lenet_conv_ciphertext(
            c1, c2, self.weights.weight_conv1, bc1, bc2, self._identity
        )
        self.phase = LeNetPhase.WAIT_AFTER_CONV1
        return EngineStepResult(
            truncate=TruncateStep(
                phase_id="after_conv1",
                client_action="relu_pool_shift",
                shift_bits=32,
                shape=list(out_c1.shape),
            ),
            output_c1=out_c1,
            output_c2=out_c2,
        )

    def accept_client_ciphertext(self, phase_id: str, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        if phase_id == "after_conv1" and self.phase == LeNetPhase.WAIT_AFTER_CONV1:
            bc1, bc2 = self._encrypt_bias(self.weights.bias_conv2)
            out_c1, out_c2 = lenet_conv_ciphertext(
                c1, c2, self.weights.weight_conv2, bc1, bc2, self._identity
            )
            self.phase = LeNetPhase.WAIT_AFTER_CONV2
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id="after_conv2",
                    client_action="relu_pool_shift",
                    shift_bits=32,
                    shape=list(out_c1.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
            )

        if phase_id == "after_conv2" and self.phase == LeNetPhase.WAIT_AFTER_CONV2:
            flat_c1, flat_c2 = flatten_ciphertext(c1, c2)
            out_c1, out_c2 = lenet_fc_layer(
                flat_c1, flat_c2,
                self.weights.weight_c3, self.weights.bias_c3,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._order,
            )
            self.phase = LeNetPhase.WAIT_AFTER_C3
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id="after_c3",
                    client_action="relu_then_shift",
                    shift_bits=32,
                    shape=list(out_c1.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
            )

        if phase_id == "after_c3" and self.phase == LeNetPhase.WAIT_AFTER_C3:
            out_c1, out_c2 = lenet_fc_layer(
                c1, c2,
                self.weights.weight_fc4, self.weights.bias_fc4,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._order,
            )
            self.phase = LeNetPhase.WAIT_AFTER_FC4
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id="after_fc4",
                    client_action="relu_then_shift",
                    shift_bits=32,
                    shape=list(out_c1.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
            )

        if phase_id == "after_fc4" and self.phase == LeNetPhase.WAIT_AFTER_FC4:
            out_c1, out_c2 = lenet_fc_layer(
                c1, c2,
                self.weights.weight_fc5, self.weights.bias_fc5,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._order,
            )
            self.phase = LeNetPhase.DONE
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id="after_fc5",
                    client_action="logits_only",
                    shift_bits=None,
                    shape=list(out_c1.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
                inference_complete=True,
            )

        raise ValueError(f"unexpected phase_id={phase_id!r} in state {self.phase}")
