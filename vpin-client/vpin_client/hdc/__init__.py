"""HDC — Homomorphic Deployable Compiler (同态可部署编译器).

Public surface:
- ``scale_rules``         §2–§3 fixed-point scale constants & rules
- ``layer_ir``            LayerNode / LayerGraph + formula scale tables (Π)
- ``model_decomposer``    G_family registry + Decompose(weights, family)
- ``range_propagate``     §4–§6 magnitude propagation + range_ok
- ``compile_deploy_plan`` §7–§8 Compile → HomomorphicDeployPlan
- ``data_adapters``       §1 raw sample → encryptable fixed-point tensor
"""

from __future__ import annotations

from vpin_client.hdc import scale_rules
from vpin_client.hdc.compile_deploy_plan import (
    HomomorphicDeployPlan,
    compile_deploy_plan,
)
from vpin_client.hdc.layer_ir import (
    CheckpointSpec,
    LayerGraph,
    LayerNode,
    build_lenet_cifar_graph,
    build_network_a_graph,
)
from vpin_client.hdc.model_decomposer import (
    build_layer_graph,
    decompose,
    family_supports_dataset,
    list_families,
)
from vpin_client.hdc.range_propagate import RangeReport, propagate_ranges

__all__ = [
    "scale_rules",
    "CheckpointSpec",
    "LayerGraph",
    "LayerNode",
    "HomomorphicDeployPlan",
    "RangeReport",
    "build_layer_graph",
    "build_lenet_cifar_graph",
    "build_network_a_graph",
    "compile_deploy_plan",
    "decompose",
    "family_supports_dataset",
    "list_families",
    "propagate_ranges",
]
