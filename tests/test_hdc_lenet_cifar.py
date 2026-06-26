"""HDC LeNet-CIFAR tests (§13 formula vs actual, dataset gates)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vpin-client"))
sys.path.insert(0, str(REPO / "vpin-backend"))

from model_training.network_lenet.truncation_config import (
    DEFAULT_PLAN,
    INTRINSIC_SHIFT_FC,
    INTRINSIC_SHIFT_POOL,
)
from model_training.network_lenet.verify import run_verify
from vpin_backend.pipeline.gates import DatasetModelMismatchError, assert_dataset_model_compatible
from vpin_client.hdc.layer_ir import build_lenet_cifar_graph, build_network_a_graph


def test_pi_formula_matches_actual():
    plan = DEFAULT_PLAN
    assert plan.shift_pool == INTRINSIC_SHIFT_POOL == 28
    assert plan.shift_fc1 == INTRINSIC_SHIFT_FC == 32

    graph = build_lenet_cifar_graph()
    formula = {c.id: (c.from_bits, c.to_bits) for c in graph.formula_scale_table()}
    for phase in plan.phases():
        assert phase.phase_id in formula
        fb, tb = formula[phase.phase_id]
        assert phase.from_bits == fb, phase.phase_id
        assert phase.to_bits == tb, phase.phase_id

    report = run_verify(None)
    assert report["pi_match"] is True


def test_reject_network_a_on_cifar():
    with pytest.raises(DatasetModelMismatchError):
        assert_dataset_model_compatible(
            model_id="cnn-mnist-trained",
            network="A",
            dataset="cifar10",
        )
    with pytest.raises(DatasetModelMismatchError):
        assert_dataset_model_compatible(
            model_id="cnn-mnist-trained",
            network="A",
            input_shape=[3, 32, 32],
        )


def test_cifar10_compile_independent_calibration():
    """LeNet graph scales must differ from Network A pool scale (28 vs 26)."""
    lenet = build_lenet_cifar_graph()
    net_a = build_network_a_graph()
    lenet_pool = next(n for n in lenet.nodes if n.op == "sum_pool")
    net_a_pool = next(n for n in net_a.nodes if n.op == "sum_pool")
    assert lenet_pool.f_out == 28
    assert net_a_pool.f_out == 26
    assert lenet_pool.f_out != net_a_pool.f_out
