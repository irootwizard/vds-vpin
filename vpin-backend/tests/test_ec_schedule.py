"""EC witness schedule loader (paper_proof counts)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "vpin-backend"))

from vpin_backend.inference.ec_schedule import load_paper_proof_counts


def test_paper_proof_counts_network_a() -> None:
    counts = load_paper_proof_counts("A")
    assert counts.num_pt_mul == 178
    assert counts.num_pt_add == 2144
    assert counts.source
