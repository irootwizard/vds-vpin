//! Static model parameters **W** (conv / FC), separate from SNARK witness `weight.json`.
//!
//! See `README.md` in this directory for load order vs `trace/`.
//! Registry / future DB: [`store::ModelStore`], [`record::ModelRecord`].

pub mod manifest;
pub mod params;
pub mod record;
pub mod store;

pub use manifest::{ModelManifest, ModelSource, VpinNpyLayout};
pub use params::{ConvHyper, ConvParams, FcParams, ModelParams, PoolHyper};
pub use record::{
    CommitmentStatus, ModelCommitmentSlot, ModelIndexEntry, ModelRecord, ModelStoreIndex,
    TruncateCheckpoint, TruncationPlanSlot, TruncationPlanStatus,
};
pub use store::{
    attach_commitment_to_record, JsonFileModelStore, ModelStore, StoreError,
};

mod load;

pub use load::{
    load_from_export_path, load_from_manifest, load_model_params, load_w_star, FullWeightsJson,
    ModelLoadError, NETWORK_A_W_STAR_LEN,
};
