use libspartan::{SNARK, SNARKGens};
use merlin::Transcript;

use crate::challenge::append_challenge_to_transcript;
use crate::circuit::mac_rlc::build::build_mac_rlc_circuit;
use crate::circuit::mac_rlc::MacRlcProof;
use crate::commit::{append_commitments_to_transcript, InputCommitmentBundle, ModelCommitmentBundle};
use crate::challenge::ClientChallenge;
use crate::statement::ServerLinearProofStack;

pub fn prove_mac_rlc_snark(
    stack: &ServerLinearProofStack,
    challenge: &ClientChallenge,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
) -> Result<MacRlcProof, String> {
    let circuit = build_mac_rlc_circuit(stack, challenge)?;
    let gens = SNARKGens::new(
        circuit.num_cons,
        circuit.num_vars,
        circuit.num_inputs,
        circuit.num_non_zero,
    );
    let (comm, decomm) = SNARK::encode(&circuit.inst, &gens);

    let mut transcript = Transcript::new(b"cp_snark_vpin");
    append_commitments_to_transcript(&mut transcript, model, input);
    append_challenge_to_transcript(&mut transcript, challenge);
    transcript.append_message(b"sub_circuit", b"mac_rlc_conv_eq9");

    let proof = SNARK::prove(
        &circuit.inst,
        &comm,
        &decomm,
        circuit.vars,
        &circuit.inputs,
        &gens,
        &mut transcript,
    );

    let public_inputs_hex: Vec<String> = circuit
        .inputs
        .assignment
        .iter()
        .map(|s| hex::encode(s.to_bytes()))
        .collect();

    Ok(MacRlcProof {
        proof_bytes: bincode::serialize(&proof).map_err(|e| e.to_string())?,
        circuit_id: "mac_rlc_conv_eq9".to_string(),
        num_cons: circuit.num_cons,
        num_vars: circuit.num_vars,
        num_inputs: circuit.num_inputs,
        num_non_zero: circuit.num_non_zero,
        public_inputs_hex,
    })
}
