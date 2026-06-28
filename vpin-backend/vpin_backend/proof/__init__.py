"""Proof plan and EC witness bundle (mirrors Rust witness API)."""

from vpin_backend.proof.ec_witness_bundle import EcWitnessBundle, load_ec_witness_from_run
from vpin_backend.proof.proof_plan import ModelProofContext, ProofPlan
from vpin_backend.proof.registry import (
    default_run_dir,
    load_proof_plan,
    register_proof_plan,
    resolve_proof_plan,
    resolve_run_dir,
)

__all__ = [
    "EcWitnessBundle",
    "ModelProofContext",
    "ProofPlan",
    "default_run_dir",
    "load_ec_witness_from_run",
    "load_proof_plan",
    "register_proof_plan",
    "resolve_proof_plan",
    "resolve_run_dir",
]
