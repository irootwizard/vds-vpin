"""HDC §2–§3 layer IR: ``LayerNode`` / ``LayerGraph`` and formula scale tables.

A ``LayerGraph`` is a linear sequence of ``LayerNode``s with fixed-point scales
derived purely from :mod:`vpin_client.hdc.scale_rules`. The ordered subset of
nodes carrying a client op (ReLU / shift / relu_then_shift / relu_only) defines
the checkpoint plan Π = (π_1, …, π_K) (§3 截断时机).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vpin_client.hdc import scale_rules as sr

# Client op vocabulary (matches vpin_client.crypto.ahe.activation.apply_client_action).
CLIENT_OPS = frozenset({"relu", "shift", "relu_then_shift", "relu_only"})
SHIFT_OPS = frozenset({"shift", "relu_then_shift"})


@dataclass(frozen=True)
class LayerNode:
    """A single op edge in the LayerGraph.

    Attributes
    ----------
    op:           one of encrypt|conv|relu|sum_pool|fc (server / structural op).
    name:         unique node id.
    f_in/f_out:   fixed-point fractional scales (§3).
    client_op:    client truncate action at this node's checkpoint (or None).
    checkpoint:   π id when this node ends a client checkpoint.
    params:       op specific metadata (channels, kernel, k, inv_bits, dims, ...).
    """

    op: str
    name: str
    f_in: int
    f_out: int
    client_op: str | None = None
    checkpoint: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def is_checkpoint(self) -> bool:
        return self.checkpoint is not None and self.client_op is not None

    @property
    def is_shift(self) -> bool:
        return self.client_op in SHIFT_OPS

    def to_dict(self) -> dict[str, Any]:
        d = {
            "op": self.op,
            "name": self.name,
            "f_in": self.f_in,
            "f_out": self.f_out,
        }
        if self.client_op is not None:
            d["client_op"] = self.client_op
        if self.checkpoint is not None:
            d["checkpoint"] = self.checkpoint
        if self.params:
            d["params"] = dict(self.params)
        return d


@dataclass(frozen=True)
class CheckpointSpec:
    """One π_k entry of the formula scale table."""

    id: str
    client_op: str
    from_bits: int
    to_bits: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "client_op": self.client_op,
            "from_bits": self.from_bits,
            "to_bits": self.to_bits,
        }


@dataclass
class LayerGraph:
    family: str
    adapter_id: str
    input_shape: tuple[int, ...]
    nodes: list[LayerNode] = field(default_factory=list)

    def add(self, node: LayerNode) -> LayerNode:
        self.nodes.append(node)
        return node

    def checkpoints(self) -> list[LayerNode]:
        """Topologically ordered Π (nodes carrying a client op)."""
        return [n for n in self.nodes if n.client_op is not None]

    def shift_checkpoints(self) -> list[LayerNode]:
        return [n for n in self.nodes if n.is_shift]

    def formula_scale_table(self) -> list[CheckpointSpec]:
        """§11.4 / §13.1 predicted from_bits/to_bits per π_k (formula side)."""
        table: list[CheckpointSpec] = []
        for n in self.checkpoints():
            cp_id = n.checkpoint or n.name
            table.append(
                CheckpointSpec(
                    id=cp_id,
                    client_op=n.client_op or "",
                    from_bits=n.f_in,
                    to_bits=n.f_out,
                )
            )
        return table

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "adapter_id": self.adapter_id,
            "input_shape": list(self.input_shape),
            "nodes": [n.to_dict() for n in self.nodes],
            "checkpoints": [c.to_dict() for c in self.formula_scale_table()],
        }


def build_lenet_cifar_graph(*, inv_bits: int = 10, k: int = 2) -> LayerGraph:
    """G_family = lenet_cifar (§11.3 / §11.4): 3×32 dual conv + 2×2 sum pool + 3 FC.

    Checkpoints Π = (π1..π6); fc3 output stays at f=32 (argmax, no client回传).
    """
    F = sr.F
    f_pool = sr.sum_pool_scale(F, k, inv_bits)  # 16 + 2 + 10 = 28
    f_fc = sr.fc_scale(F)  # 32
    g = LayerGraph(family="lenet_cifar", adapter_id="cifar_rgb", input_shape=(3, 32, 32))

    g.add(LayerNode("encrypt", "encrypt", f_in=F, f_out=F, params={"shape": [3, 32, 32]}))
    g.add(
        LayerNode(
            "conv", "conv1", f_in=F, f_out=sr.conv_relu_scale(F),
            params={"in_ch": 3, "out_ch": 6, "kernel": 5, "out_shape": [6, 28, 28]},
        )
    )
    g.add(
        LayerNode(
            "relu", "after_conv1", f_in=F, f_out=F,
            client_op="relu", checkpoint="after_conv1",
            params={"shape": [6, 28, 28]},
        )
    )
    g.add(
        LayerNode(
            "sum_pool", "pool1", f_in=F, f_out=f_pool,
            params={"k": k, "inv_bits": inv_bits, "average": False, "out_shape": [6, 14, 14]},
        )
    )
    g.add(
        LayerNode(
            "relu", "after_pool1", f_in=f_pool, f_out=F,
            client_op="shift", checkpoint="after_pool1",
            params={"shape": [6, 14, 14]},
        )
    )
    g.add(
        LayerNode(
            "conv", "conv2", f_in=F, f_out=sr.conv_relu_scale(F),
            params={"in_ch": 6, "out_ch": 16, "kernel": 5, "out_shape": [16, 10, 10]},
        )
    )
    g.add(
        LayerNode(
            "relu", "after_conv2", f_in=F, f_out=F,
            client_op="relu", checkpoint="after_conv2",
            params={"shape": [16, 10, 10]},
        )
    )
    g.add(
        LayerNode(
            "sum_pool", "pool2", f_in=F, f_out=f_pool,
            params={"k": k, "inv_bits": inv_bits, "average": False, "out_shape": [16, 5, 5]},
        )
    )
    g.add(
        LayerNode(
            "relu", "after_pool2", f_in=f_pool, f_out=F,
            client_op="shift", checkpoint="after_pool2",
            params={"shape": [16, 5, 5]},
        )
    )
    g.add(LayerNode("fc", "fc1", f_in=F, f_out=f_fc, params={"in": 400, "out": 120}))
    g.add(
        LayerNode(
            "relu", "after_fc1", f_in=f_fc, f_out=F,
            client_op="relu_then_shift", checkpoint="after_fc1",
            params={"shape": [120]},
        )
    )
    g.add(LayerNode("fc", "fc2", f_in=F, f_out=f_fc, params={"in": 120, "out": 84}))
    g.add(
        LayerNode(
            "relu", "after_fc2", f_in=f_fc, f_out=F,
            client_op="relu_then_shift", checkpoint="after_fc2",
            params={"shape": [84]},
        )
    )
    g.add(LayerNode("fc", "fc3", f_in=F, f_out=f_fc, params={"in": 84, "out": 10}))
    return g


def build_network_a_graph(*, inv_bits: int = 10, k: int = 4) -> LayerGraph:
    """G_family = network_a (§10) — MNIST reference track, 4×4 avg-pool variant (f_pool=26)."""
    F = sr.F
    f_pool = sr.sum_pool_avg_scale(F, inv_bits)  # 26
    f_fc = sr.fc_scale(F)  # 32
    g = LayerGraph(family="network_a", adapter_id="mnist", input_shape=(1, 28, 28))

    g.add(LayerNode("encrypt", "encrypt", f_in=F, f_out=F, params={"shape": [1, 32, 32]}))
    g.add(LayerNode("conv", "conv", f_in=F, f_out=F, params={"kernel": 3, "fixed_kernel": True}))
    g.add(
        LayerNode(
            "relu", "after_conv", f_in=F, f_out=F,
            client_op="relu", checkpoint="after_conv",
        )
    )
    g.add(
        LayerNode(
            "sum_pool", "pool", f_in=F, f_out=f_pool,
            params={"k": k, "inv_bits": inv_bits, "average": True, "out_shape": [1, 8, 8]},
        )
    )
    g.add(
        LayerNode(
            "relu", "after_pool", f_in=f_pool, f_out=F,
            client_op="shift", checkpoint="after_pool",
        )
    )
    g.add(LayerNode("fc", "fc1", f_in=F, f_out=f_fc, params={"in": 64, "out": 16}))
    g.add(
        LayerNode(
            "relu", "after_fc1", f_in=f_fc, f_out=F,
            client_op="relu_then_shift", checkpoint="after_fc1",
        )
    )
    g.add(LayerNode("fc", "fc2", f_in=F, f_out=f_fc, params={"in": 16, "out": 10}))
    g.add(
        LayerNode(
            "relu", "after_fc2", f_in=f_fc, f_out=f_fc,
            client_op="relu_only", checkpoint="after_fc2",
        )
    )
    return g
