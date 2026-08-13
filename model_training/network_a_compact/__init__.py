"""Network A compact variant: client round-trips only at ReLU boundaries (no shift rounds)."""

from model_training.network_a_compact.model import NetworkACompact, QuantMode

__all__ = ["NetworkACompact", "QuantMode"]
