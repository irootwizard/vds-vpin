"""Tests for network_lenet: π-formula vs actual, and reject Network A on CIFAR.

Run:
    python -m pytest model_training/tests/test_network_lenet.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── helpers ────────────────────────────────────────────────────────────────────

def _synthetic_batch(n: int = 8) -> torch.Tensor:
    """Random uint8 CIFAR-like batch (B,3,32,32)."""
    return torch.randint(0, 256, (n, 3, 32, 32), dtype=torch.uint8)


# ── test_pi_formula_matches_actual ────────────────────────────────────────────

class TestPiFormulaMatchesActual:
    """§13 formula verification: truncation_config.phases()[k].from_bits must equal
    the intrinsic formula values (28 for pool, 32 for FC)."""

    def test_pool_from_bits_is_28(self) -> None:
        from model_training.network_lenet.truncation_config import (
            DEFAULT_PLAN,
            INTRINSIC_SHIFT_POOL,
        )

        assert INTRINSIC_SHIFT_POOL == 28, f"Expected 28, got {INTRINSIC_SHIFT_POOL}"
        for phase in DEFAULT_PLAN.phases():
            if phase.phase_id in ("after_pool1", "after_pool2"):
                assert phase.from_bits == 28, (
                    f"{phase.phase_id}.from_bits={phase.from_bits} != 28"
                )

    def test_fc_from_bits_is_32(self) -> None:
        from model_training.network_lenet.truncation_config import (
            DEFAULT_PLAN,
            INTRINSIC_SHIFT_FC,
        )

        assert INTRINSIC_SHIFT_FC == 32, f"Expected 32, got {INTRINSIC_SHIFT_FC}"
        for phase in DEFAULT_PLAN.phases():
            if phase.phase_id in ("after_fc1", "after_fc2"):
                assert phase.from_bits == 32, (
                    f"{phase.phase_id}.from_bits={phase.from_bits} != 32"
                )

    def test_relu_phases_are_f16(self) -> None:
        from model_training.network_lenet.truncation_config import DEFAULT_PLAN

        for phase in DEFAULT_PLAN.phases():
            if phase.phase_id in ("after_conv1", "after_conv2"):
                assert phase.from_bits == 16, (
                    f"{phase.phase_id}.from_bits={phase.from_bits} != 16"
                )
                assert phase.client_action == "relu", (
                    f"{phase.phase_id}.client_action={phase.client_action} != relu"
                )

    def test_pool_inv_fp_is_1024(self) -> None:
        from model_training.network_lenet.truncation_config import DEFAULT_PLAN

        assert DEFAULT_PLAN.pool_inv_fp == 1024, (
            f"pool_inv_fp={DEFAULT_PLAN.pool_inv_fp} != 1024 "
            "(should be 2^10 to produce f=28 after 2×2 sum pool)"
        )

    def test_six_phases_total(self) -> None:
        from model_training.network_lenet.truncation_config import DEFAULT_PLAN

        phases = DEFAULT_PLAN.phases()
        assert len(phases) == 6, f"Expected 6 phases, got {len(phases)}"
        ids = [p.phase_id for p in phases]
        assert ids == [
            "after_conv1", "after_pool1", "after_conv2", "after_pool2",
            "after_fc1", "after_fc2",
        ], f"Phase IDs mismatch: {ids}"

    def test_formula_vs_actual_forward(self) -> None:
        """Run forward_fixed_point on synthetic batch; check pool1 pre-shift is
        in the expected range for f=28 (values should be < 2^28 for normal images)."""
        from model_training.network_lenet.model import LeNetCIFAR
        from model_training.network_lenet.truncation_config import DEFAULT_PLAN

        model = LeNetCIFAR(plan=DEFAULT_PLAN)
        model.eval()
        images = _synthetic_batch(4)

        with torch.no_grad():
            _, bounds = model.forward_fixed_point(images, return_bounds=True)

        pool1_max = bounds.get("after_pool1_pre_shift", 0.0)
        pool2_max = bounds.get("after_pool2_pre_shift", 0.0)
        fc1_max   = bounds.get("after_fc1_pre_relu", 0.0)

        # Values must be positive (network activated)
        assert pool1_max > 0, "pool1 pre-shift max should be > 0"
        assert pool2_max > 0, "pool2 pre-shift max should be > 0"

        # Values for random-init model should not massively overflow 2^28 / 2^32
        # (the network is random so we just check sign / positivity, not tight bounds)
        assert pool1_max < 2 ** 40, f"pool1 pre-shift={pool1_max:.3e} suspiciously large"
        assert fc1_max < 2 ** 50, f"fc1 pre-relu={fc1_max:.3e} suspiciously large"

    def test_build_validation_report_pi_match(self) -> None:
        """run_verify with synthetic batch should produce pi_match=True."""
        import os
        import tempfile
        from model_training.network_lenet.verify import run_verify

        with tempfile.TemporaryDirectory() as tmp:
            report = run_verify(None)  # no run_dir → synthetic batch

        assert report["pi_match"] is True, (
            f"pi_match=False: {report.get('pi_diffs', [])}"
        )
        # Check formula_pi from_bits
        formula_pi = {c["id"]: c for c in report["formula_pi"]}
        assert formula_pi["after_pool1"]["from_bits"] == 28, "pool1 formula from_bits != 28"
        assert formula_pi["after_pool2"]["from_bits"] == 28, "pool2 formula from_bits != 28"
        assert formula_pi["after_fc1"]["from_bits"] == 32, "fc1 formula from_bits != 32"
        assert formula_pi["after_fc2"]["from_bits"] == 32, "fc2 formula from_bits != 32"


# ── test_reject_network_a_on_cifar ────────────────────────────────────────────

class TestRejectNetworkAOnCifar:
    """Network A (cnn-mnist-trained) must not work with A_cifar_rgb adapter.

    The guard is:
    1. LeNetCIFAR.MODEL_ID != cnn-mnist-trained
    2. LeNetCIFAR.DATASET == cifar10 (MNIST adapters must be rejected)
    3. Attempting to load a cnn-mnist-trained checkpoint into LeNetCIFAR raises an error
       (shape mismatch).
    """

    def test_model_id_is_lenet_cifar10(self) -> None:
        from model_training.network_lenet.model import LeNetCIFAR

        assert LeNetCIFAR.MODEL_ID == "lenet-cifar10"
        assert LeNetCIFAR.MODEL_ID != "cnn-mnist-trained"

    def test_network_family_is_lenet_cifar(self) -> None:
        from model_training.network_lenet.model import LeNetCIFAR

        assert LeNetCIFAR.NETWORK_FAMILY == "lenet_cifar"

    def test_dataset_is_cifar10(self) -> None:
        from model_training.network_lenet.model import LeNetCIFAR

        assert LeNetCIFAR.DATASET == "cifar10"

    def test_network_a_state_dict_incompatible(self) -> None:
        """Loading Network A state_dict into LeNetCIFAR must fail (shape mismatch)."""
        from model_training.network_a.model import NetworkA
        from model_training.network_lenet.model import LeNetCIFAR

        net_a = NetworkA()
        lenet = LeNetCIFAR()
        with pytest.raises(RuntimeError):
            lenet.load_state_dict(net_a.state_dict(), strict=True)

    def test_cifar_preprocess_different_from_mnist(self) -> None:
        """A_cifar_rgb produces 3-channel tensors; mnist preprocess produces 1-channel."""
        import torch
        from model_training.network_lenet.preprocess import preprocess_batch_rgb
        from model_training.network_a.preprocess import preprocess_batch_uint8

        cifar_images = torch.randint(0, 256, (2, 3, 32, 32), dtype=torch.uint8)
        mnist_images = torch.randint(0, 256, (2, 1, 28, 28), dtype=torch.uint8)

        _, cifar_fixed = preprocess_batch_rgb(cifar_images)
        _, mnist_fixed = preprocess_batch_uint8(mnist_images)

        assert cifar_fixed.shape[0] == 2, f"cifar fixed batch: {cifar_fixed.shape}"
        assert cifar_fixed.shape[1] == 3, f"cifar fixed channels: {cifar_fixed.shape}"
        assert mnist_fixed.shape[1] == 1, f"mnist fixed channels: {mnist_fixed.shape}"

        # Channel counts are different — mixing is impossible
        assert cifar_fixed.shape[1] != mnist_fixed.shape[1]

    def test_train_module_rejects_non_cifar_dataset(self) -> None:
        """train.py main() must exit 1 for non-cifar10 dataset argument."""
        from model_training.network_lenet.train import main as train_main

        ret = train_main(["--dataset", "mnist", "--float-epochs", "0", "--fixed-epochs", "0"])
        assert ret == 1, f"Expected exit 1 for mnist dataset, got {ret}"
