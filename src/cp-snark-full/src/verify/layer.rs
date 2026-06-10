//! M5 verify orchestration for per-layer π.

use crate::circuit::layer::{verify_layer_stack, LayerProofBundle};

pub fn verify_layers(bundle: &LayerProofBundle) -> bool {
    verify_layer_stack(bundle)
}
