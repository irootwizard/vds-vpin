//! Toy network Eq.(7) sum pool: `pool_out = Σ_i pool_in[i]`.
//!
//! Toy parameters: 1 window of 4 values (the 4 conv outputs). The activation
//! / scaling chain is performed off-circuit in AHE per the paper; only the
//! linear sum is bound to the SNARK here.
//!
//! ## R1CS layout
//! | Range            | Role         | Goes into     |
//! |------------------|--------------|---------------|
//! | `0..NW*K`        | pool_in[k][i]| `vars_input`  |
//! | `NW*K..NW*K+NW`  | pool_out[k]  | `vars_input`  |
//!
//! Constraint per window k: `(Σ_i pool_in[k][i]) * 1 = pool_out[k]`.

use std::time::Instant;

use libspartan::scalar::Scalar;
use libspartan::{InputsAssignment, Instance, VarsAssignment};

use crate::challenge::ClientChallenge;
use crate::circuit_prove::{
    prove_sub_circuit_with_cm_w, verify_sub_circuit_with_cm_w, CircuitWitness,
};
use crate::commit::cps::CpsCommitment;
use crate::commit::{InputCommitmentBundle, ModelCommitmentBundle};
use crate::curve::embed_u128_to_scalar;
use crate::protocol::artifacts::SubCircuitProof;

pub const TOY_NUM_WINDOWS: usize = 1;
pub const TOY_WINDOW_SIZE: usize = 4;

const NW: usize = TOY_NUM_WINDOWS;
const K: usize = TOY_WINDOW_SIZE;
const NUM_VARS: usize = NW * K + NW;
const NUM_INPUTS: usize = 1;
const NUM_CONS: usize = NW;

pub const TOY_POOL_NUM_VARS: usize = NUM_VARS;
pub const TOY_POOL_NUM_CONS: usize = NUM_CONS;

#[derive(Clone, Debug)]
pub struct PoolToyTrace {
    pub windows: Vec<Vec<u128>>,
    pub outputs: Vec<u128>,
}

impl PoolToyTrace {
    pub fn validate(&self) -> Result<(), String> {
        if self.windows.len() != NW {
            return Err(format!(
                "pool toy: num_windows {} != {}",
                self.windows.len(),
                NW
            ));
        }
        for (k, w) in self.windows.iter().enumerate() {
            if w.len() != K {
                return Err(format!(
                    "pool toy: window {k} size {} != {}",
                    w.len(),
                    K
                ));
            }
        }
        if self.outputs.len() != NW {
            return Err(format!(
                "pool toy: outputs len {} != {}",
                self.outputs.len(),
                NW
            ));
        }
        Ok(())
    }
}

fn in_idx(k: usize, i: usize) -> usize {
    debug_assert!(k < NW && i < K);
    k * K + i
}

fn out_idx(k: usize) -> usize {
    debug_assert!(k < NW);
    NW * K + k
}

/// Build the deterministic Spartan R1CS instance for the toy sum pool.
pub fn build_pool_toy_instance() -> Instance {
    let one = Scalar::one().to_bytes();
    let mut a: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut b: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut c: Vec<(usize, usize, [u8; 32])> = Vec::new();

    for k in 0..NW {
        let row = k;
        for i in 0..K {
            a.push((row, in_idx(k, i), one));
        }
        b.push((row, NUM_VARS, one));
        c.push((row, out_idx(k), one));
    }

    Instance::new(NUM_CONS, NUM_VARS, NUM_INPUTS, &a, &b, &c)
        .expect("pool_toy R1CS instance")
}

fn approx_num_non_zero() -> usize {
    let a_count = NW * K;
    let b_count = NW;
    let c_count = NW;
    a_count.max(b_count).max(c_count).next_power_of_two().max(2)
}

pub fn build_pool_toy_witness(trace: &PoolToyTrace) -> Result<CircuitWitness, String> {
    trace.validate()?;
    let inst = build_pool_toy_instance();

    let mut vars_para_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_input_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];

    for k in 0..NW {
        for i in 0..K {
            let s = embed_u128_to_scalar(trace.windows[k][i]);
            vars_input_bytes[in_idx(k, i)] = s.to_bytes();
            vars_bytes[in_idx(k, i)] = s.to_bytes();
        }
        let os = embed_u128_to_scalar(trace.outputs[k]);
        vars_input_bytes[out_idx(k)] = os.to_bytes();
        vars_bytes[out_idx(k)] = os.to_bytes();
    }
    let _ = &vars_para_bytes;

    let assignment_inputs = InputsAssignment::new(&[Scalar::one().to_bytes()])
        .map_err(|e| format!("pool_toy inputs: {e:?}"))?;
    let assignment_vars_para =
        VarsAssignment::new(&vars_para_bytes).map_err(|e| format!("pool_toy vars_para: {e:?}"))?;
    let assignment_vars_input = VarsAssignment::new(&vars_input_bytes)
        .map_err(|e| format!("pool_toy vars_input: {e:?}"))?;
    let assignment_vars =
        VarsAssignment::new(&vars_bytes).map_err(|e| format!("pool_toy vars: {e:?}"))?;

    let sat = inst
        .is_sat(&assignment_vars, &assignment_inputs)
        .map_err(|e| format!("pool_toy is_sat error: {e:?}"))?;
    if !sat {
        return Err("pool_toy R1CS unsatisfied".to_string());
    }

    let num_padded = inst.inst.get_num_vars();
    let pad = |a: VarsAssignment| {
        if num_padded > a.assignment.len() {
            a.pad(num_padded)
        } else {
            a
        }
    };

    Ok(CircuitWitness {
        num_cons: NUM_CONS,
        num_vars: NUM_VARS,
        num_inputs: NUM_INPUTS,
        num_non_zero: approx_num_non_zero(),
        inst,
        padded_vars_para: pad(assignment_vars_para),
        padded_vars_input: pad(assignment_vars_input),
        padded_vars: pad(assignment_vars),
        assignment_inputs,
    })
}

pub fn prove_pool_toy(
    trace: &PoolToyTrace,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    prove_pool_toy_with_cm_w(trace, None, model, input, challenge)
}

pub fn prove_pool_toy_with_cm_w(
    trace: &PoolToyTrace,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    let witness = build_pool_toy_witness(trace)?;
    let t0 = Instant::now();
    let proof = prove_sub_circuit_with_cm_w("pool_toy", witness, cps_cm_w, model, input, challenge);
    Ok((proof, t0.elapsed().as_millis()))
}

pub fn verify_pool_toy(
    proof: &SubCircuitProof,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    verify_pool_toy_with_cm_w(proof, None, model, input, challenge)
}

pub fn verify_pool_toy_with_cm_w(
    proof: &SubCircuitProof,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    if proof.circuit_name != "pool_toy" {
        return Err(format!(
            "verify_pool_toy: unexpected circuit_name {}",
            proof.circuit_name
        ));
    }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        verify_sub_circuit_with_cm_w(proof, "pool_toy", cps_cm_w, model, input, challenge)
    }))
    .map_err(|_| "verify_pool_toy: spartan upstream panic on invalid proof".to_string())
    .and_then(|r| r)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_trace() -> PoolToyTrace {
        PoolToyTrace {
            windows: vec![vec![48, 56, 80, 88]],
            outputs: vec![272],
        }
    }

    fn assert_err_contains(res: Result<CircuitWitness, String>, needle: &str) {
        match res {
            Ok(_) => panic!("expected error containing {needle:?}, got Ok"),
            Err(e) => assert!(e.contains(needle), "got error {e:?}, want {needle:?}"),
        }
    }

    #[test]
    fn satisfiability_honest_trace() {
        let _ = build_pool_toy_witness(&toy_trace()).expect("honest witness");
    }

    #[test]
    fn negative_wrong_sum() {
        let mut t = toy_trace();
        t.outputs[0] = 271;
        assert_err_contains(build_pool_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_wrong_input() {
        let mut t = toy_trace();
        t.windows[0][2] = 79;
        assert_err_contains(build_pool_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_shape_mismatch() {
        let mut t = toy_trace();
        t.windows[0].pop();
        assert_err_contains(build_pool_toy_witness(&t), "size");
    }
}
