use libspartan::{InputsAssignment, SNARK, SNARKGens};
use merlin::Transcript;

use crate::challenge::append_challenge_to_transcript;
use crate::circuit::mac_rlc::build::build_mac_rlc_circuit;
use crate::circuit::mac_rlc::MacRlcProof;
use crate::commit::append_commitments_to_transcript;
use crate::protocol::ProtocolArtifacts;
use crate::trace::build_stack_for_network;

pub fn verify_mac_rlc_snark(mac: &MacRlcProof, artifacts: &ProtocolArtifacts) -> Result<(), String> {
    let proof: libspartan::SNARK =
        bincode::deserialize(&mac.proof_bytes).map_err(|e| format!("deserialize mac proof: {e}"))?;

    let witness = build_stack_for_network(&artifacts.network)
        .map_err(|e| format!("rebuild stack for mac verify: {e:?}"))?;

    let circuit = build_mac_rlc_circuit(&witness.stack, &artifacts.client_challenge)?;

    let gens = SNARKGens::new(
        circuit.num_cons,
        circuit.num_vars,
        circuit.num_inputs,
        circuit.num_non_zero,
    );
    let (comm, _) = SNARK::encode(&circuit.inst, &gens);

    let inputs_bytes: Vec<[u8; 32]> = mac
        .public_inputs_hex
        .iter()
        .map(|h| {
            let b = hex::decode(h).map_err(|e| format!("input hex: {e}"))?;
            if b.len() != 32 {
                return Err(format!("expected 32 bytes, got {}", b.len()));
            }
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&b);
            Ok(arr)
        })
        .collect::<Result<_, String>>()?;
    let assignment_inputs =
        InputsAssignment::new(&inputs_bytes).map_err(|e| format!("inputs assignment: {e:?}"))?;

    let mut transcript = Transcript::new(b"cp_snark_vpin");
    append_commitments_to_transcript(
        &mut transcript,
        &artifacts.model_commitment,
        &artifacts.input_commitment,
    );
    append_challenge_to_transcript(&mut transcript, &artifacts.client_challenge);
    transcript.append_message(b"sub_circuit", b"mac_rlc_conv_eq9");

    proof
        .verify(&comm, &assignment_inputs, &mut transcript, &gens)
        .map_err(|e| format!("mac_rlc verify: {e}"))
}
