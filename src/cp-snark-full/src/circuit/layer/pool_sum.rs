//! π_pool: Eq. (7) in-circuit (M5.2 structured stub).

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PoolSumProofStub {
    pub layer_id: u8,
    pub window_count: usize,
}

pub fn prove_pool_sum_stub(network: &str) -> Option<Vec<u8>> {
    let _ = network;
    let stub = PoolSumProofStub {
        layer_id: 0,
        window_count: 0,
    };
    serde_json::to_vec(&stub).ok()
}

pub fn verify_pool_sum_stub(proof: Option<&Vec<u8>>) -> bool {
    match proof {
        None => true,
        Some(p) => !p.is_empty(),
    }
}
