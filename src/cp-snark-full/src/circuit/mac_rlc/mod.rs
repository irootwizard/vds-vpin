//! MAC + RLC R1CS for conv (9) and FC (10).

mod build;
mod prove;
mod verify;

pub use build::build_mac_rlc_circuit;
pub use prove::prove_mac_rlc_snark;
pub use verify::verify_mac_rlc_snark;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MacRlcProof {
    pub proof_bytes: Vec<u8>,
    pub circuit_id: String,
    pub num_cons: usize,
    pub num_vars: usize,
    pub num_inputs: usize,
    pub num_non_zero: usize,
    pub public_inputs_hex: Vec<String>,
}
