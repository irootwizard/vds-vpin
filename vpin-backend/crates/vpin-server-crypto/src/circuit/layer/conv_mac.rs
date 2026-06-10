//! Toy network Eq.(9) conv MAC: `out[k] = Σ_i filter[i] · window[k][i]`.
//!
//! Toy parameters: `num_filter = 9`, `num_windows = 4` (3×3 filter on 4×4 valid conv).
//!
//! ## R1CS layout (logical)
//! Variable indices (0-based, in a single VarsAssignment of length `num_vars`):
//!
//! | Range                                      | Role             | Goes into     |
//! |--------------------------------------------|------------------|---------------|
//! | `0..num_filter`                            | filter[i]        | `vars_para`   |
//! | `num_filter..num_filter+nw*nk`             | window[k][i]     | `vars_input`  |
//! | `num_filter+nw*nk..num_filter+2*nw*nk`     | t[k][i] = w·x    | `vars_input`  |
//! | `num_filter+2*nw*nk..num_filter+2*nw*nk+nw`| out[k]           | `vars_input`  |
//!
//! Constraints (per window k, per filter i):
//! - mul: `filter[i] * window[k][i] = t[k][i]`
//! - sum: `(Σ_i t[k][i]) * 1 = out[k]`
//!
//! Total: `num_cons = nw * (nk + 1)` (40 for the toy), `num_vars = nf + 2*nw*nk + nw` (85).

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

pub const TOY_NUM_FILTER: usize = 9;
pub const TOY_NUM_WINDOWS: usize = 4;

#[derive(Clone, Debug)]
pub struct ConvToyTrace {
    pub filter: Vec<u128>,
    pub windows: Vec<Vec<u128>>,
    pub outputs: Vec<u128>,
}

impl ConvToyTrace {
    pub fn validate(&self) -> Result<(), String> {
        if self.filter.len() != TOY_NUM_FILTER {
            return Err(format!(
                "conv toy: filter len {} != {}",
                self.filter.len(),
                TOY_NUM_FILTER
            ));
        }
        if self.windows.len() != TOY_NUM_WINDOWS {
            return Err(format!(
                "conv toy: num_windows {} != {}",
                self.windows.len(),
                TOY_NUM_WINDOWS
            ));
        }
        for (k, w) in self.windows.iter().enumerate() {
            if w.len() != TOY_NUM_FILTER {
                return Err(format!(
                    "conv toy: window {k} len {} != {}",
                    w.len(),
                    TOY_NUM_FILTER
                ));
            }
        }
        if self.outputs.len() != TOY_NUM_WINDOWS {
            return Err(format!(
                "conv toy: outputs len {} != {}",
                self.outputs.len(),
                TOY_NUM_WINDOWS
            ));
        }
        Ok(())
    }
}

const NF: usize = TOY_NUM_FILTER;
const NW: usize = TOY_NUM_WINDOWS;
const NK: usize = TOY_NUM_FILTER;
const NUM_CONS_PER_WINDOW: usize = NK + 1;
const NUM_CONS: usize = NW * NUM_CONS_PER_WINDOW;
const NUM_VARS: usize = NF + 2 * NW * NK + NW;
const NUM_INPUTS: usize = 1;

pub const TOY_CONV_NUM_CONS: usize = NUM_CONS;
pub const TOY_CONV_NUM_VARS: usize = NUM_VARS;
pub const TOY_CONV_NUM_INPUTS: usize = NUM_INPUTS;

fn filter_idx(i: usize) -> usize {
    debug_assert!(i < NF);
    i
}

fn window_idx(k: usize, i: usize) -> usize {
    debug_assert!(k < NW && i < NK);
    NF + k * NK + i
}

fn t_idx(k: usize, i: usize) -> usize {
    debug_assert!(k < NW && i < NK);
    NF + NW * NK + k * NK + i
}

fn out_idx(k: usize) -> usize {
    debug_assert!(k < NW);
    NF + 2 * NW * NK + k
}

/// Build the deterministic Spartan R1CS instance for the toy conv MAC.
///
/// Used by both prover (with witness) and verifier (rebuild on verify).
pub fn build_conv_toy_instance() -> Instance {
    let one = Scalar::one().to_bytes();
    let mut a: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut b: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut c: Vec<(usize, usize, [u8; 32])> = Vec::new();

    for k in 0..NW {
        for i in 0..NK {
            let row = k * NUM_CONS_PER_WINDOW + i;
            // filter[i] * window[k][i] = t[k][i]
            a.push((row, filter_idx(i), one));
            b.push((row, window_idx(k, i), one));
            c.push((row, t_idx(k, i), one));
        }
        let sum_row = k * NUM_CONS_PER_WINDOW + NK;
        // (Σ_i t[k][i]) * 1 = out[k]
        for i in 0..NK {
            a.push((sum_row, t_idx(k, i), one));
        }
        b.push((sum_row, NUM_VARS, one));
        c.push((sum_row, out_idx(k), one));
    }

    Instance::new(NUM_CONS, NUM_VARS, NUM_INPUTS, &a, &b, &c)
        .expect("conv_toy R1CS instance construction failed")
}

/// Spartan requires `num_nz_entries == max(|A|, |B|, |C|).next_power_of_two()`.
///
/// For the toy conv:
/// - `|A| = NW * (NK + NK) = 72` (9 mul rows × 1 entry + 4 sum rows × 9 entries).
/// - `|B| = NW * (NK + 1) = 40`.
/// - `|C| = NW * (NK + 1) = 40`.
fn approx_num_non_zero() -> usize {
    let a_count = NW * NK + NW * NK; // mul A col + sum A cols
    let b_count = NW * NK + NW; // mul B col + sum B col (constant 1)
    let c_count = NW * NK + NW; // mul C col + sum C col
    let max_count = a_count.max(b_count).max(c_count);
    max_count.next_power_of_two()
}

/// Build a [`CircuitWitness`] honest with respect to the supplied trace.
///
/// Returns an error if the trace shape is wrong; satisfiability is checked
/// here and surfaces as `Err("conv_toy R1CS unsatisfied")` if the trace's
/// `out[k] != Σ_i filter[i] · window[k][i]` (used by negative tests).
pub fn build_conv_toy_witness(trace: &ConvToyTrace) -> Result<CircuitWitness, String> {
    trace.validate()?;
    let inst = build_conv_toy_instance();

    let mut vars_para_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_input_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];
    let mut vars_bytes = vec![Scalar::zero().to_bytes(); NUM_VARS];

    for i in 0..NF {
        let s = embed_u128_to_scalar(trace.filter[i]);
        vars_para_bytes[filter_idx(i)] = s.to_bytes();
        vars_bytes[filter_idx(i)] = s.to_bytes();
    }

    for k in 0..NW {
        for i in 0..NK {
            let xs = embed_u128_to_scalar(trace.windows[k][i]);
            vars_input_bytes[window_idx(k, i)] = xs.to_bytes();
            vars_bytes[window_idx(k, i)] = xs.to_bytes();

            let ws = embed_u128_to_scalar(trace.filter[i]);
            let ts = ws * xs;
            vars_input_bytes[t_idx(k, i)] = ts.to_bytes();
            vars_bytes[t_idx(k, i)] = ts.to_bytes();
        }
        let os = embed_u128_to_scalar(trace.outputs[k]);
        vars_input_bytes[out_idx(k)] = os.to_bytes();
        vars_bytes[out_idx(k)] = os.to_bytes();
    }

    let assignment_inputs = InputsAssignment::new(&[Scalar::one().to_bytes()])
        .map_err(|e| format!("conv_toy inputs: {e:?}"))?;

    let assignment_vars_para =
        VarsAssignment::new(&vars_para_bytes).map_err(|e| format!("conv_toy vars_para: {e:?}"))?;
    let assignment_vars_input =
        VarsAssignment::new(&vars_input_bytes).map_err(|e| format!("conv_toy vars_input: {e:?}"))?;
    let assignment_vars =
        VarsAssignment::new(&vars_bytes).map_err(|e| format!("conv_toy vars: {e:?}"))?;

    let sat = inst
        .is_sat(&assignment_vars, &assignment_inputs)
        .map_err(|e| format!("conv_toy is_sat error: {e:?}"))?;
    if !sat {
        return Err("conv_toy R1CS unsatisfied".to_string());
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

/// Prove the toy conv layer R1CS (Eq. 9 MAC).
pub fn prove_conv_toy(
    trace: &ConvToyTrace,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    prove_conv_toy_with_cm_w(trace, None, model, input, challenge)
}

/// Phase Z.8: prove conv layer with the canonical Spartan PC `cm_W` woven
/// into the SNARK transcript.
pub fn prove_conv_toy_with_cm_w(
    trace: &ConvToyTrace,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(SubCircuitProof, u128), String> {
    let witness = build_conv_toy_witness(trace)?;
    let t0 = Instant::now();
    let proof = prove_sub_circuit_with_cm_w("conv_toy", witness, cps_cm_w, model, input, challenge);
    Ok((proof, t0.elapsed().as_millis()))
}

/// Verify a toy conv layer proof. Returns `Ok(())` on success.
///
/// **Note on panics**: upstream Spartan (`nizk/mod.rs:576`) uses `assert_eq!`
/// on a recomputed group element before returning Err — so tampered proof bytes
/// can trigger a panic instead of `Err`. We catch that here and surface it as
/// `Err("verify panic: ...")`.
pub fn verify_conv_toy(
    proof: &SubCircuitProof,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    verify_conv_toy_with_cm_w(proof, None, model, input, challenge)
}

/// Phase Z.8 verifier counterpart of [`prove_conv_toy_with_cm_w`].
pub fn verify_conv_toy_with_cm_w(
    proof: &SubCircuitProof,
    cps_cm_w: Option<&CpsCommitment>,
    model: &ModelCommitmentBundle,
    input: &InputCommitmentBundle,
    challenge: &ClientChallenge,
) -> Result<(), String> {
    if proof.circuit_name != "conv_toy" {
        return Err(format!(
            "verify_conv_toy: unexpected circuit_name {}",
            proof.circuit_name
        ));
    }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        verify_sub_circuit_with_cm_w(proof, "conv_toy", cps_cm_w, model, input, challenge)
    }))
    .map_err(|_| "verify_conv_toy: spartan upstream panic on invalid proof".to_string())
    .and_then(|r| r)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_trace() -> ConvToyTrace {
        ConvToyTrace {
            filter: vec![1, 0, 1, 2, 0, 2, 1, 0, 1],
            windows: vec![
                vec![1, 2, 3, 5, 6, 7, 9, 10, 11],
                vec![2, 3, 4, 6, 7, 8, 10, 11, 12],
                vec![5, 6, 7, 9, 10, 11, 13, 14, 15],
                vec![6, 7, 8, 10, 11, 12, 14, 15, 16],
            ],
            outputs: vec![48, 56, 80, 88],
        }
    }

    #[test]
    fn satisfiability_honest_trace() {
        let w = build_conv_toy_witness(&toy_trace()).expect("honest witness");
        assert_eq!(w.num_cons, NUM_CONS);
        assert_eq!(w.num_vars, NUM_VARS);
    }

    fn assert_err_contains(res: Result<CircuitWitness, String>, needle: &str) {
        match res {
            Ok(_) => panic!("expected error containing {needle:?}, got Ok"),
            Err(e) => assert!(e.contains(needle), "got error {e:?}, want {needle:?}"),
        }
    }

    #[test]
    fn negative_wrong_filter() {
        let mut t = toy_trace();
        t.filter[0] = 99;
        assert_err_contains(build_conv_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_wrong_window() {
        let mut t = toy_trace();
        t.windows[0][0] = 42;
        assert_err_contains(build_conv_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_wrong_output() {
        let mut t = toy_trace();
        t.outputs[2] = 999;
        assert_err_contains(build_conv_toy_witness(&t), "unsatisfied");
    }

    #[test]
    fn negative_shape_mismatch() {
        let mut t = toy_trace();
        t.windows.pop();
        assert_err_contains(build_conv_toy_witness(&t), "num_windows");
    }
}
