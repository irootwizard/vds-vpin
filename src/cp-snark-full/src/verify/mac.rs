use crate::circuit::mac_rlc::{verify_mac_rlc_snark, MacRlcProof};
use crate::protocol::ProtocolArtifacts;

pub fn verify_mac_rlc(mac: &MacRlcProof, artifacts: &ProtocolArtifacts) -> Result<(), String> {
    verify_mac_rlc_snark(mac, artifacts)
}
