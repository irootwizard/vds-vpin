//! M5 prove orchestration for per-layer π.

use crate::circuit::layer::{prove_layer_stack, LayerProofBundle, LayerProveError};

pub fn prove_layers_for_network(network: &str) -> Result<LayerProofBundle, LayerProveError> {
    prove_layer_stack(network)
}
