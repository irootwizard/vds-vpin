//! π_fc[k]: Eq. (10) compressed in-circuit (M5.3 structured stub).

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FcMacProofStub {
    pub layer_index: u8,
    pub out_dim: usize,
}

pub fn prove_fc_mac_stubs(network: &str) -> Vec<Vec<u8>> {
    let _ = network;
    vec![]
}

pub fn prove_fc_mac_stub(layer_index: u8, out_dim: usize) -> Option<Vec<u8>> {
    let stub = FcMacProofStub {
        layer_index,
        out_dim,
    };
    serde_json::to_vec(&stub).ok()
}

pub fn verify_fc_mac_stubs(proofs: &[Vec<u8>]) -> bool {
    proofs.iter().all(|p| p.is_empty())
}

pub fn verify_fc_mac_stub(proof: Option<&Vec<u8>>) -> bool {
    match proof {
        None => true,
        Some(p) => !p.is_empty(),
    }
}
