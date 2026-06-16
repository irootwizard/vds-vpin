//! M5: per-layer in-circuit π (π_conv / π_pool / π_fc).

pub mod conv_mac;
pub mod fc_mac;
pub mod pool_sum;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct LayerProofBundle {
    pub pi_conv: Option<Vec<u8>>,
    pub pi_pool: Option<Vec<u8>>,
    pub pi_fc: Vec<Vec<u8>>,
}

#[derive(Clone, Debug)]
pub enum LayerProveError {
    NotImplemented(String),
}

impl std::fmt::Display for LayerProveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LayerProveError::NotImplemented(m) => write!(f, "layer prove not implemented: {m}"),
        }
    }
}

impl std::error::Error for LayerProveError {}

/// Prove all layer SNARKs (M5 entry — structured stubs until R1CS wired).
pub fn prove_layer_stack(network: &str) -> Result<LayerProofBundle, LayerProveError> {
    Ok(LayerProofBundle {
        pi_conv: conv_mac::prove_conv_mac_stub(network),
        pi_pool: pool_sum::prove_pool_sum_stub(network),
        pi_fc: fc_mac::prove_fc_mac_stubs(network),
    })
}

pub fn verify_layer_stack(bundle: &LayerProofBundle) -> bool {
    conv_mac::verify_conv_mac_stub(bundle.pi_conv.as_ref())
        && pool_sum::verify_pool_sum_stub(bundle.pi_pool.as_ref())
        && fc_mac::verify_fc_mac_stubs(&bundle.pi_fc)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn layer_stub_roundtrip() {
        let b = prove_layer_stack("A").unwrap();
        assert!(verify_layer_stack(&b));
    }
}
