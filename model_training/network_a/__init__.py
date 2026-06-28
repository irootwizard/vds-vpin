"""Network A MNIST training — topology aligned with AHE inference."""

from model_training.network_a.ec_witness_schedule import (
    EcWitnessMode,
    LayerEcCounts,
    NetworkAGridSpec,
    NetworkAEcSchedule,
    derive_ec_schedule,
    derive_paper_proof_layers,
    derive_paper_proof_schedule,
    load_standard_grid_spec,
    write_ec_schedule_bundle,
    write_ec_schedule_json,
)

__all__ = [
    "EcWitnessMode",
    "LayerEcCounts",
    "NetworkAGridSpec",
    "NetworkAEcSchedule",
    "derive_ec_schedule",
    "derive_paper_proof_layers",
    "derive_paper_proof_schedule",
    "load_standard_grid_spec",
    "write_ec_schedule_bundle",
    "write_ec_schedule_json",
]
