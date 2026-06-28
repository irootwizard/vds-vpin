//! Model-export EC witness bundle (per-run `proof_artifacts/ec_witness/`).

pub mod bundle;
pub mod schedule;

pub use bundle::{
    discover_run_bundle, load_ec_witness, load_ec_witness_from_run_dir, set_active_ec_witness_root,
    active_ec_witness_root, clear_active_ec_witness_root, EcWitnessBundle, EcWitnessManifest,
    EcWitnessManifestLayer, ModelProofContext, ProofPlan,
};
pub use schedule::{EcWitnessLayerSchedule, EcWitnessSchedule};
