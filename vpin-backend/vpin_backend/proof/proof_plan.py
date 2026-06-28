"""Compiled proof plan for one model run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vpin_backend.proof.ec_witness_bundle import EcWitnessBundle, load_ec_witness_from_run


@dataclass(frozen=True)
class ProofPlan:
    model_id: str
    run_dir: Path
    witness: EcWitnessBundle
    schedule_mode: str = "paper_proof"

    @classmethod
    def from_run_dir(
        cls,
        run_dir: Path,
        model_id: str = "A",
        mode: str = "paper_proof",
    ) -> ProofPlan:
        witness = load_ec_witness_from_run(run_dir, model_id=model_id)
        return cls(
            model_id=model_id,
            run_dir=run_dir.resolve(),
            witness=witness,
            schedule_mode=mode,
        )


@dataclass(frozen=True)
class ModelProofContext:
    model_id: str
    run_dir: Path
    witness: EcWitnessBundle

    @classmethod
    def from_plan(cls, plan: ProofPlan) -> ModelProofContext:
        return cls(
            model_id=plan.model_id,
            run_dir=plan.run_dir,
            witness=plan.witness,
        )
