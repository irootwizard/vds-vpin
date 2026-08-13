"""Tests: paper-derived EC witness counts (arXiv:2411.07468 Table I)."""

from __future__ import annotations

import unittest

from model_training.network_a.ec_witness_schedule import (
    EcWitnessMode,
    NetworkAGridSpec,
    derive_ec_schedule,
    derive_paper_proof_layers,
    load_standard_grid_spec,
)


class TestPaperEcWitnessSchedule(unittest.TestCase):
    def test_standard_run_grid_32(self) -> None:
        spec = load_standard_grid_spec()
        self.assertEqual(spec.input_n, 32)
        self.assertEqual(spec.conv_num_windows, 1024)
        self.assertEqual(spec.pool_flat_dim, 64)

    def test_paper_proof_table_i_network_a(self) -> None:
        """Paper Table I + B=2 branches -> 178 PtMul, 2144 PtAdd."""
        schedule = derive_ec_schedule(NetworkAGridSpec(), EcWitnessMode.PAPER_PROOF)
        self.assertEqual(schedule.total_pt_mul, 178)
        self.assertEqual(schedule.total_pt_add, 2144)
        self.assertTrue(schedule.cross_check["paper_proof_matches_legacy_ptmul"])
        self.assertTrue(schedule.cross_check["paper_proof_matches_legacy_ptadd"])

        layers = {l.layer_id: l for l in schedule.layers}
        self.assertEqual(layers["conv"].pt_mul, 18)
        self.assertEqual(layers["conv"].pt_add, 16)
        self.assertEqual(layers["pool"].pt_mul, 0)
        self.assertEqual(layers["pool"].pt_add, 1920)
        self.assertEqual(layers["fc1"].pt_mul, 128)
        self.assertEqual(layers["fc1"].pt_add, 158)
        self.assertEqual(layers["fc2"].pt_mul, 32)
        self.assertEqual(layers["fc2"].pt_add, 50)

    def test_paper_ptmul_independent_of_input_size(self) -> None:
        small = derive_ec_schedule(NetworkAGridSpec(input_n=8), EcWitnessMode.PAPER_PROOF)
        large = derive_ec_schedule(NetworkAGridSpec(input_n=32), EcWitnessMode.PAPER_PROOF)
        self.assertEqual(small.total_pt_mul, large.total_pt_mul)
        self.assertEqual(large.total_pt_mul, 178)
        self.assertLess(small.total_pt_add, large.total_pt_add)

    def test_ahe_homomorphic_scales_with_windows(self) -> None:
        small = derive_ec_schedule(NetworkAGridSpec(input_n=8), EcWitnessMode.AHE_HOMOMORPHIC)
        large = derive_ec_schedule(NetworkAGridSpec(input_n=32), EcWitnessMode.AHE_HOMOMORPHIC)
        self.assertLess(small.total_pt_mul, large.total_pt_mul)
        self.assertEqual(large.cross_check["ahe_conv_pool_ptmul"], 18560)

    def test_layer_mul_ranges_contiguous(self) -> None:
        schedule = derive_ec_schedule(mode=EcWitnessMode.PAPER_PROOF)
        expect = 0
        for layer in schedule.layers:
            self.assertEqual(layer.pt_mul_start, expect)
            expect = layer.pt_mul_end
        self.assertEqual(expect, 178)


if __name__ == "__main__":
    unittest.main()
