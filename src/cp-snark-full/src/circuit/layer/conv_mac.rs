//! π_conv: Eq. (9) RLC in-circuit (M5.1 structured stub).

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConvMacProofStub {
    pub layer_id: u8,
    pub num_mac_terms: usize,
    pub rlc_gamma_hex: String,
}

pub fn prove_conv_mac_stub(network: &str) -> Option<Vec<u8>> {
    let _ = network;
    let stub = ConvMacProofStub {
        layer_id: 0,
        num_mac_terms: 0,
        rlc_gamma_hex: String::new(),
    };
    serde_json::to_vec(&stub).ok()
}

pub fn verify_conv_mac_stub(proof: Option<&Vec<u8>>) -> bool {
    match proof {
        None => true,
        Some(p) => !p.is_empty(),
    }
}
