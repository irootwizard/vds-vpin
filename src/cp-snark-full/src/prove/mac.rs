//! π_mac (RLC compressed MAC) — conv Eq.(9) Spartan sub-circuit.

use crate::challenge::ClientChallenge;
use crate::circuit::mac_rlc::{prove_mac_rlc_snark, MacRlcProof};
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::statement::ServerLinearProofStack;

pub fn prove_mac_rlc(
    stack: &ServerLinearProofStack,
    challenge: &ClientChallenge,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
) -> Option<MacRlcProof> {
    if stack.conv.is_none() {
        return None;
    }
    prove_mac_rlc_snark(stack, challenge, model, input).ok()
}
