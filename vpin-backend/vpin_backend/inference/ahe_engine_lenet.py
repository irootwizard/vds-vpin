"""AHE inference engine for LeNet network (alternative to Network A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.inference.ahe_engine import EnginePhase, EngineStepResult, TruncateStep


class AheLenetEngine:
    """Placeholder LeNet engine — Network A uses ``AheEngine`` instead."""

    def __init__(
        self,
        *,
        public_key: Point | None = None,
        weights: object | None = None,
        network_id: str = "lenet_cifar",
        skip_return_phases: list[str] | None = None,
    ) -> None:
        self.public_key = public_key
        self.weights = weights
        self.network_id = network_id
        self.skip_return_phases = skip_return_phases or []
        self.phase = EnginePhase.WAIT_INITIAL

    @classmethod
    def for_network(
        cls,
        *,
        public_key: Point,
        weights: object,
        network_id: str,
        skip_return_phases: list[str] | None = None,
    ) -> AheLenetEngine:
        return cls(
            public_key=public_key,
            weights=weights,
            network_id=network_id,
            skip_return_phases=skip_return_phases,
        )

    def bind_initial_ciphertext(self, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        raise NotImplementedError("LeNet AHE engine is not implemented on this branch")

    def accept_client_ciphertext(self, phase_id: str, c1: np.ndarray, c2: np.ndarray) -> EngineStepResult:
        raise NotImplementedError("LeNet AHE engine is not implemented on this branch")
