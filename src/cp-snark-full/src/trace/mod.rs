//! Homomorphic inference **trace** (EC JSON + optional conv windows export).

pub mod conv;
pub mod ec;
pub mod ec_layer;
pub mod fc;
pub mod pool;

mod build;

pub use build::{
    build_linear_stack, build_linear_stack_optional, build_stack_for_network, BuildStackError,
    BuildStackInput, LinearStackWitness,
};
pub use conv::{load_conv_trace, ConvTraceBundle, ConvWitnessSource};
pub use ec::{load_ec_trace, EcTrace};
pub use ec_layer::{
    load_ec_manifest, manifest_path, slice_ec_by_layer, EcLayerManifest, EcLayerRange, EcLayerSlice,
};
