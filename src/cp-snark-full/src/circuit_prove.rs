#![allow(non_snake_case)]

use curve25519_dalek::ristretto::CompressedRistretto;
use libspartan::dense_mlpoly::{DensePolynomial, PolyCommitment};
use libspartan::random::RandomTape;
use libspartan::{InputsAssignment, Instance, SNARK, SNARKGens, VarsAssignment};
use merlin::Transcript;
use serde::{Deserialize, Serialize};

use crate::challenge::{append_challenge_to_transcript, ClientChallenge};
use crate::commit::cps::CpsCommitment;
use crate::commitment::{append_commitments_to_transcript, InputCommitmentBundle, ModelCommitmentBundle};
use crate::commit_spartan::{my_dense_mlpoly_commit, my_lib_prove, my_lib_verify};

/// Phase Z.8: append canonical Spartan PC `cm_W` before legacy Pedersen commitments.
pub fn append_cps_cm_w_to_transcript(transcript: &mut Transcript, cps_cm: &CpsCommitment) {
    transcript.append_message(b"cps_kind", cps_cm.kind.as_bytes());
    transcript.append_message(b"cps_cm_w_hex", cps_cm.cm_hex.as_bytes());
    transcript.append_message(
        b"cps_cm_w_num_scalars",
        cps_cm.num_scalars.to_le_bytes().as_ref(),
    );
    transcript.append_message(
        b"cps_cm_w_padded_len",
        cps_cm.padded_len.to_le_bytes().as_ref(),
    );
}

/// Unified transcript seed: optional `cm_W` → Pedersen cm_W/cm_x → challenge → sub_circuit.
pub fn seed_layer_transcript(
    transcript: &mut Transcript,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    name: &str,
) {
    if let Some(cm) = cps_cm_w {
        append_cps_cm_w_to_transcript(transcript, cm);
    }
    append_commitments_to_transcript(transcript, model, input);
    append_challenge_to_transcript(transcript, challenge);
    transcript.append_message(b"sub_circuit", name.as_bytes());
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SubCircuitProof {
    pub circuit_name: String,
    pub proof_bytes: Vec<u8>,
    pub public_inputs_hex: Vec<String>,
    pub comm_para_hex: Vec<String>,
    pub comm_input_hex: Vec<String>,
    pub num_cons: usize,
    pub num_vars: usize,
    pub num_inputs: usize,
    pub num_non_zero: usize,
}

pub struct CircuitWitness {
    pub num_cons: usize,
    pub num_vars: usize,
    pub num_inputs: usize,
    pub num_non_zero: usize,
    pub inst: Instance,
    pub padded_vars_para: VarsAssignment,
    pub padded_vars_input: VarsAssignment,
    pub padded_vars: VarsAssignment,
    pub assignment_inputs: InputsAssignment,
}

fn prove_sub_circuit(
    name: &str,
    witness: CircuitWitness,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> SubCircuitProof {
    let CircuitWitness {
        num_cons,
        num_vars,
        num_inputs,
        num_non_zero,
        inst,
        padded_vars_para,
        padded_vars_input,
        padded_vars,
        assignment_inputs,
    } = witness;

    let gens = SNARKGens::new(num_cons, num_vars, num_inputs, num_non_zero);
    let (comm, decomm) = SNARK::encode(&inst, &gens);

    let mut random_tape_1 = RandomTape::new(&[2u8]);

    let poly_vars_para = DensePolynomial::new(padded_vars_para.assignment.clone());
    let (comm_vars_para, blind_vars_para) =
        poly_vars_para.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut random_tape_1));

    let poly_vars_inputs = DensePolynomial::new(padded_vars_input.assignment.clone());
    let (comm_vars_input, blind_vars_input) =
        poly_vars_inputs.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut random_tape_1));

    let poly_vars = DensePolynomial::new(padded_vars.assignment.clone());
    let (comm_vars, blind_vars) = my_dense_mlpoly_commit(
        &poly_vars,
        &gens.gens_r1cs_sat.gens_pc,
        blind_vars_para.blinds.clone(),
        blind_vars_input.blinds.clone(),
    );

    let mut combine_comm_vars = vec![];
    for i in 0..comm_vars_para.C.len() {
        combine_comm_vars.push(
            (comm_vars_para.C[i].decompress().unwrap() + comm_vars_input.C[i].decompress().unwrap())
                .compress(),
        );
    }
    let combine_commitment = PolyCommitment {
        C: combine_comm_vars,
    };

    let mut prover_transcript = Transcript::new(b"cp_snark_vpin");
    seed_layer_transcript(
        &mut prover_transcript,
        cps_cm_w,
        model,
        input,
        challenge,
        name,
    );

    let proof = my_lib_prove(
        &inst,
        &decomm,
        padded_vars,
        &assignment_inputs,
        &gens,
        &mut prover_transcript,
        poly_vars,
        combine_commitment,
        blind_vars,
    );

    let public_inputs_hex: Vec<String> = assignment_inputs
        .assignment
        .iter()
        .map(|s| hex::encode(s.to_bytes()))
        .collect();
    let comm_para_hex: Vec<String> = comm_vars_para
        .C
        .iter()
        .map(|c| hex::encode(c.as_bytes()))
        .collect();
    let comm_input_hex: Vec<String> = comm_vars_input
        .C
        .iter()
        .map(|c| hex::encode(c.as_bytes()))
        .collect();

    SubCircuitProof {
        circuit_name: name.to_string(),
        proof_bytes: bincode::serialize(&proof).expect("proof serialize"),
        public_inputs_hex,
        comm_para_hex,
        comm_input_hex,
        num_cons,
        num_vars,
        num_inputs,
        num_non_zero,
    }
}

pub fn verify_sub_circuit(
    sub: &SubCircuitProof,
    network: &str,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    let proof: SNARK = bincode::deserialize(&sub.proof_bytes).map_err(|e| e.to_string())?;

    let inst = rebuild_instance(sub, network)?;
    let (comm, _decomm) = SNARK::encode(&inst, &SNARKGens::new(
        sub.num_cons,
        sub.num_vars,
        sub.num_inputs,
        sub.num_non_zero,
    ));

    let public_inputs: Vec<libspartan::scalar::Scalar> = sub
        .public_inputs_hex
        .iter()
        .map(|h| {
            let bytes = hex::decode(h).unwrap_or_else(|_| vec![0u8; 32]);
            let mut wide = [0u8; 64];
            let len = bytes.len().min(64);
            wide[..len].copy_from_slice(&bytes[..len]);
            libspartan::scalar::Scalar::from_bytes_wide(&wide)
        })
        .collect();
    let assignment_inputs = InputsAssignment { assignment: public_inputs };

    let comm_para: Vec<curve25519_dalek::ristretto::CompressedRistretto> = sub
        .comm_para_hex
        .iter()
        .map(|h| {
            let bytes = hex::decode(h).unwrap();
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&bytes);
            CompressedRistretto(arr)
        })
        .collect();
    let comm_input_pts: Vec<curve25519_dalek::ristretto::CompressedRistretto> = sub
        .comm_input_hex
        .iter()
        .map(|h| {
            let bytes = hex::decode(h).unwrap();
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&bytes);
            CompressedRistretto(arr)
        })
        .collect();

    let comm_vars_para = PolyCommitment { C: comm_para };
    let comm_vars_input = PolyCommitment { C: comm_input_pts };

    let gens = SNARKGens::new(
        sub.num_cons,
        sub.num_vars,
        sub.num_inputs,
        sub.num_non_zero,
    );

    let mut verifier_transcript = Transcript::new(b"cp_snark_vpin");
    seed_layer_transcript(
        &mut verifier_transcript,
        cps_cm_w,
        model,
        input,
        challenge,
        &sub.circuit_name,
    );

    my_lib_verify(
        proof,
        &comm,
        &assignment_inputs,
        &mut verifier_transcript,
        &gens,
        comm_vars_para,
        comm_vars_input,
    )
    .map_err(|e| format!("verify error: {:?}", e))
}

fn rebuild_instance(sub: &SubCircuitProof, network: &str) -> Result<Instance, String> {
    let inst = match sub.circuit_name.as_str() {
        "point_add" => {
            let (num_cons, num_vars, num_inputs, num_non_zero, inst, _, _, _, _) =
                crate::point_addition::point_addition(network);
            assert_eq!(num_cons, sub.num_cons);
            inst
        }
        "point_mult" => {
            let (num_cons, num_vars, num_inputs, num_non_zero, inst, _, _, _, _) =
                crate::point_mult::point_mult(network);
            assert_eq!(num_cons, sub.num_cons);
            inst
        }
        other => return Err(format!("unknown circuit: {other}")),
    };
    Ok(inst)
}

pub fn prove_point_add(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    cps_cm_w: Option<&CpsCommitment>,
) -> SubCircuitProof {
    let (
        num_cons,
        num_vars,
        num_inputs,
        num_non_zero,
        inst,
        padded_vars_para,
        padded_vars_input,
        padded_vars,
        assignment_inputs,
    ) = crate::point_addition::point_addition(network);

    prove_sub_circuit(
        "point_add",
        CircuitWitness {
            num_cons,
            num_vars,
            num_inputs,
            num_non_zero,
            inst,
            padded_vars_para,
            padded_vars_input,
            padded_vars,
            assignment_inputs,
        },
        cps_cm_w,
        model,
        input,
        challenge,
    )
}

pub fn prove_point_mult(
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    cps_cm_w: Option<&CpsCommitment>,
) -> SubCircuitProof {
    let (
        num_cons,
        num_vars,
        num_inputs,
        num_non_zero,
        inst,
        padded_vars_para,
        padded_vars_input,
        padded_vars,
        assignment_inputs,
    ) = crate::point_mult::point_mult(network);

    prove_sub_circuit(
        "point_mult",
        CircuitWitness {
            num_cons,
            num_vars,
            num_inputs,
            num_non_zero,
            inst,
            padded_vars_para,
            padded_vars_input,
            padded_vars,
            assignment_inputs,
        },
        cps_cm_w,
        model,
        input,
        challenge,
    )
}

pub fn verify_point_add(
    sub: &SubCircuitProof,
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    cps_cm_w: Option<&CpsCommitment>,
) -> Result<(), String> {
    verify_sub_circuit(sub, network, cps_cm_w, model, input, challenge)
}

pub fn verify_point_mult(
    sub: &SubCircuitProof,
    network: &str,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
    cps_cm_w: Option<&CpsCommitment>,
) -> Result<(), String> {
    verify_sub_circuit(sub, network, cps_cm_w, model, input, challenge)
}
