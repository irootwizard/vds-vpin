"""Proof plan, EC witness, M1 verify, and artifact helpers."""

from vpin_backend.proof.artifacts import (
    challenge_from_artifact,
    challenge_wire_from_artifact,
    commitments_from_artifact,
    load_artifact_json,
)
from vpin_backend.proof.ec_witness_bundle import EcWitnessBundle, load_ec_witness_from_run
from vpin_backend.proof.m1_verify import load_traces_from_run, verify_artifact_m1
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
    "challenge_from_artifact",
    "challenge_wire_from_artifact",
    "commitments_from_artifact",
    "default_run_dir",
    "load_artifact_json",
    "load_ec_witness_from_run",
    "load_proof_plan",
    "load_traces_from_run",
    "register_proof_plan",
    "resolve_proof_plan",
    "resolve_run_dir",
    "verify_artifact_m1",
]
