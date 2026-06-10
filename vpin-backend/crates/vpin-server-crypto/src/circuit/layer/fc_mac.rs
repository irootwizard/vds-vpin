//! Toy network Eq.(10) FC MAC + bias: `out[j] = weight[j] · input + bias[j]`.
//!
//! Toy parameters: `fc_in = 1`, `fc_out = 2`. Input is the pool output; the
//! weights+bias are the model parameters and go into `vars_para`.
//!
//! ## R1CS layout (logical)
//! | Range            | Role              | Goes into     |
//! |------------------|-------------------|---------------|
//! | `0..F_OUT`       | weight[j]         | `vars_para`   |
//! | `F_OUT..2*F_OUT` | bias[j]           | `vars_para`   |
//! | `2*F_OUT..2*F_OUT+1`              | input               | `vars_input` |
//! | `2*F_OUT+1..3*F_OUT+1`            | t[j] = w[j] · input | `vars_input` |
//! | `3*F_OUT+1..4*F_OUT+1`            | out[j] = t[j]+bias[j]| `vars_input` |
//!
//! Constraints per j:
//! - mul: `weight[j] * input = t[j]`
//! - add: `(t[j] + bias[j]) * 1 = out[j]`

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

pub const TOY_FC_IN: usize = 1;
pub const TOY_FC_OUT: usize = 2;

const F_OUT: usize = TOY_FC_OUT;
const NUM_VARS: usize = 4 * F_OUT + 1;
const NUM_CONS: usize = 2 * F_OUT;
const NUM_INPUTS: usize = 1;

pub const TOY_FC_NUM_VARS: usize = NUM_VARS;
pub const TOY_FC_NUM_CONS: usize = NUM_CONS;

#[derive(Clone, Debug)]
pub struct FcToyTrace {
    pub input: u128,
    pub weights: Vec<u128>,
    pub bias: Vec<u128>,
    pub outputs: Vec<u128>,
}

impl FcToyTrace {
    pub fn validate(&self) -> Result<(), String> {
        if self.weights.len() != F_OUT {
            return Err(format!("fc toy: weights len {} != {F_OUT}", self.weights.len()));
        }
        if self.bias.len() != F_OUT {
            return Err(format!("fc toy: bias len {} != {F_OUT}", self.bias.len()));
        }
        if self.outputs.len() != F_OUT {
            return Err(format!("fc toy: outputs len {} != {F_OUT}", self.outputs.len()));
        }
        Ok(())
    }
}

fn weight_idx(j: usize) -> usize {
    debug_assert!(j < F_OUT);
    j
}

fn bias_idx(j: usize) -> usize {
    debug_assert!(j < F_OUT);
    F_OUT + j
}

fn input_idx() -> usize {
    2 * F_OUT
}

fn t_idx(j: usize) -> usize {
    debug_assert!(j < F_OUT);
    2 * F_OUT + 1 + j
}

fn out_idx(j: usize) -> usize {
    debug_assert!(j < F_OUT);
    3 * F_OUT + 1 + j
}

/// Build the deterministic Spartan R1CS instance for the toy FC MAC + bias.
pub fn build_fc_toy_instance() -> Instance {
    let one = Scalar::one().to_bytes();
    let mut a: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut b: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut c: Vec<(usize, usize, [u8; 32])> = Vec::new();

    for j in 0..F_OUT {
        // mul: weight[j] * input = t[j]
        let row_mul = 2 * j;
        a.push((row_mul, weight_idx(j), one));
        b.push((row_mul, input_idx(), one));
        c.push((row_mul, t_idx(j), one));

        // add: (t[j] + bias[j]) * 1 = out[j]
        let row_add = 2 * j + 1;
        a.push((row_add, t_idx(j), one));
        a.push((row_add, bias_idx(j), one));
        b.push((row_add, NUM_VARS, one));
        c.push((row_add, out_idx(j), one));
    }

    Instance::new(NUM_CONS, NUM_VARS, NUM_INPUTS, &a, &b, &c)
        .expect("fc_toy R1CS instance")
}

fn approx_num_non_zero() -> usize {
    let a_count = F_OUT + 2 * F_OUT; // mul A 1 + add A 2
    let b_count = F_OUT + F_OUT;
    let c_count = F_OUT + F_OUT;
    a_count.max(b_count).max(c_count).next_power_of_two().max(2)
}

pub fn build_fc_toy_witness(trace: &FcToyTrace) -> Result<CircuitWitness, String> {
    trace.validate()?;
    let inst = build_fc_toy_instance();

    let mut vars_para_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_input_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];

    let input_s = embed_u128_to_scalar(trace.input);
    vars_input_bytes[input_idx()] = input_s.to_bytes();
    vars_bytes[input_idx()] = input_s.to_bytes();

    for j in 0..F_OUT {
        let w = embed_u128_to_scalar(trace.weights[j]);
        let b_j = embed_u128_to_scalar(trace.bias[j]);
        vars_para_bytes[weight_idx(j)] = w.to_bytes();
        vars_para_bytes[bias_idx(j)] = b_j.to_bytes();
        vars_bytes[weight_idx(j)] = w.to_bytes();
        vars_bytes[bias_idx(j)] = b_j.to_bytes();

        let t = w * input_s;
        vars_input_bytes[t_idx(j)] = t.to_bytes();
        vars_bytes[t_idx(j)] = t.to_bytes();

        let out_s = embed_u128_to_scalar(trace.outputs[j]);
        vars_input_bytes[out_idx(j)] = out_s.to_bytes();
        vars_bytes[out_idx(j)] = out_s.to_bytes();
    }

    let assignment_inputs = InputsAssignment::new(&[Scalar::one().to_bytes()])
        .map_err(|e| format!("fc_toy inputs: {e:?}"))?;
    let assignment_vars_para =
        VarsAssignment::new(&vars_para_bytes).map_err(|e| format!("fc_toy vars_para: {e:?}"))?;
    let assignment_vars_input =
        VarsAssignment::new(&vars_input_bytes).map_err(|e| format!("fc_toy vars_input: {e:?}"))?;
    let assignment_vars =
        VarsAssignment::new(&vars_bytes).map_err(|e| format!("fc_toy vars: {e:?}"))?;

    let sat = inst
        .is_sat(&assignment_vars, &assignment_inputs)
        .map_err(|e| format!("fc_toy is_sat error: {e:?}"))?;
    if !sat {
        return Err("fc_toy R1CS unsatisfied".to_string());
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

pub fn prove_fc_toy(
    trace: &FcToyTrace,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    prove_fc_toy_with_cm_w(trace, None, model, input, challenge)
}

pub fn prove_fc_toy_with_cm_w(
    trace: &FcToyTrace,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    let witness = build_fc_toy_witness(trace)?;
    let t0 = Instant::now();
    let proof = prove_sub_circuit_with_cm_w("fc_toy", witness, cps_cm_w, model, input, challenge);
    Ok((proof, t0.elapsed().as_millis()))
}

pub fn verify_fc_toy(
    proof: &SubCircuitProof,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    verify_fc_toy_with_cm_w(proof, None, model, input, challenge)
}

pub fn verify_fc_toy_with_cm_w(
    proof: &SubCircuitProof,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    if proof.circuit_name != "fc_toy" {
        return Err(format!(
            "verify_fc_toy: unexpected circuit_name {}",
            proof.circuit_name
        ));
    }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        verify_sub_circuit_with_cm_w(proof, "fc_toy", cps_cm_w, model, input, challenge)
    }))
    .map_err(|_| "verify_fc_toy: spartan upstream panic on invalid proof".to_string())
    .and_then(|r| r)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_trace() -> FcToyTrace {
        FcToyTrace {
            input: 272,
            weights: vec![2, 3],
            bias: vec![5, 7],
            outputs: vec![549, 823],
        }
    }

    fn assert_err_contains(res: Result<CircuitWitness, String>, needle: &str) {
        match res {
            Ok(_) => panic!("expected error containing {needle:?}, got Ok"),
            Err(e) => assert!(e.contains(needle), "got {e:?}, want {needle:?}"),
        }
    }

    #[test]
    fn satisfiability_honest_trace() {
        let _ = build_fc_toy_witness(&toy_trace()).expect("honest witness");
    }

    #[test]
    fn negative_wrong_weight() {
        let mut t = toy_trace();
        t.weights[0] = 99;
        assert_err_contains(build_fc_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_wrong_bias() {
        let mut t = toy_trace();
        t.bias[1] = 0;
        assert_err_contains(build_fc_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_wrong_output() {
        let mut t = toy_trace();
        t.outputs[0] = 500;
        assert_err_contains(build_fc_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_shape_mismatch() {
        let mut t = toy_trace();
        t.bias.pop();
        assert_err_contains(build_fc_toy_witness(&t), "bias len");
    }
}
