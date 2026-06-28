"""AHE inference session state machine (P3 only) — Network A/B shared conv+pool path."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.curve import curve_e2_info
from vpin_backend.crypto.ahe.topology import NETWORK_A, NetworkTopology, get_topology
from vpin_backend.inference.homomorphic_network_a import (
    NetworkAWeights,
    avg_pool_ciphertext,
    conv2_ciphertext,
    fc1_layer,
    fc2_layer,
    flatten_ciphertext,
    get_op_counters,
    load_network_a_weights,
    reset_op_counters,
)


class EnginePhase(str, Enum):
    WAIT_INITIAL = "wait_initial"
    WAIT_AFTER_CONV = "wait_after_conv"
    WAIT_AFTER_POOL = "wait_after_pool"
    WAIT_AFTER_FC1 = "wait_after_fc1"
    DONE = "done"


@dataclass
class TruncateStep:
    phase_id: str
    client_action: str
    shift_bits: int | None
    shape: list[int]


@dataclass
class EngineStepResult:
    truncate: TruncateStep | None = None
    output_c1: np.ndarray | None = None
    output_c2: np.ndarray | None = None
    inference_complete: bool = False
    num_pt_add: int = 0
    num_pt_mult: int = 0


@dataclass
class AheEngine:
    public_key: Point
    weights: NetworkAWeights = field(default_factory=load_network_a_weights)
    topology: NetworkTopology = field(default_factory=lambda: NETWORK_A)
    phase: EnginePhase = EnginePhase.WAIT_INITIAL
    _curve_base_field: int = field(init=False)
    _curve_order: int = field(init=False)
    _generator: Point = field(init=False)
    _identity: Point = field(init=False)
    _pool_kernel: int = field(init=False)
    _pool_stride: int = field(init=False)
    _pending_c1: np.ndarray | None = None
    _pending_c2: np.ndarray | None = None

    def __post_init__(self) -> None:
        _, base_field, order, generator, identity = curve_e2_info()
        self._curve_base_field = base_field
        self._curve_order = order
        self._generator = generator
        self._identity = identity
        self._pool_kernel = self.topology.pools[0].kernel_h
        self._pool_stride = self.topology.pools[0].stride
        reset_op_counters()

    @classmethod
    def for_network(
        cls,
        public_key: Point,
        weights: NetworkAWeights,
        network_id: str,
    ) -> AheEngine:
        return cls(public_key=public_key, weights=weights, topology=get_topology(network_id))

    def bind_initial_ciphertext(self, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        if self.phase != EnginePhase.WAIT_INITIAL:
            raise ValueError(f"unexpected phase {self.phase}")
        out_c1, out_c2 = conv2_ciphertext(c1, c2, self._identity)
        self.phase = EnginePhase.WAIT_AFTER_CONV
        step = self.topology.truncation_phases[0]
        return EngineStepResult(
            truncate=TruncateStep(
                phase_id=step.phase_id,
                client_action=step.client_action,
                shift_bits=step.shift_bits,
                shape=list(step.shape),
            ),
            output_c1=out_c1,
            output_c2=out_c2,
        )

    def accept_client_ciphertext(self, phase_id: str, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        if phase_id == "after_conv" and self.phase == EnginePhase.WAIT_AFTER_CONV:
            pool_c1, pool_c2 = avg_pool_ciphertext(
                c1, c2, self._identity, self._pool_kernel, self._pool_stride
            )
            flat_c1, flat_c2 = flatten_ciphertext(pool_c1, pool_c2)
            self.phase = EnginePhase.WAIT_AFTER_POOL
            step = self.topology.truncation_phases[1]
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id=step.phase_id,
                    client_action=step.client_action,
                    shift_bits=step.shift_bits,
                    shape=list(step.shape),
                ),
                output_c1=flat_c1,
                output_c2=flat_c2,
            )

        if phase_id == "after_pool" and self.phase == EnginePhase.WAIT_AFTER_POOL:
            out_c1, out_c2 = fc1_layer(
                self.weights,
                c1,
                c2,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._curve_order,
            )
            self.phase = EnginePhase.WAIT_AFTER_FC1
            step = self.topology.truncation_phases[2]
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id=step.phase_id,
                    client_action=step.client_action,
                    shift_bits=step.shift_bits,
                    shape=list(step.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
            )

        if phase_id == "after_fc1" and self.phase == EnginePhase.WAIT_AFTER_FC1:
            out_c1, out_c2 = fc2_layer(
                self.weights,
                c1,
                c2,
                generator=self._generator,
                public_key=self.public_key,
                curve_order=self._curve_order,
            )
            self.phase = EnginePhase.DONE
            step = self.topology.truncation_phases[3]
            add, mult = get_op_counters()
            return EngineStepResult(
                truncate=TruncateStep(
                    phase_id=step.phase_id,
                    client_action=step.client_action,
                    shift_bits=step.shift_bits,
                    shape=list(step.shape),
                ),
                output_c1=out_c1,
                output_c2=out_c2,
                inference_complete=True,
                num_pt_add=add,
                num_pt_mult=mult,
            )

        raise ValueError(f"invalid phase transition: phase_id={phase_id} engine={self.phase}")
