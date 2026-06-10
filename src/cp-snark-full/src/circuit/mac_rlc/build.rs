//! **DEPRECATED (design 2026-06-10):** stub circuit — left/right computed outside R1CS.
//! Do not wire into `prover_pipeline` (`mac_proof=None`). Target: per-layer in-circuit π_conv.
//! See `docs/cp-snark-分层证明与RLC设计定稿.md`. Eq.(9) compute path: `Server.py` rLCL/rLCR.

use libspartan::scalar::Scalar;
use libspartan::{InputsAssignment, Instance, VarsAssignment};

use crate::challenge::ClientChallenge;
use crate::layer_proof::rlc::{conv_rlc_left, conv_rlc_right};
use crate::layer_proof::ConvLayerProofSpec;
use crate::statement::ServerLinearProofStack;

pub struct MacRlcCircuit {
    pub num_cons: usize,
    pub num_vars: usize,
    pub num_inputs: usize,
    pub num_non_zero: usize,
    pub inst: Instance,
    pub vars: VarsAssignment,
    pub inputs: InputsAssignment,
}

fn scalar_bytes(s: &Scalar) -> [u8; 32] {
    s.to_bytes()
}

/// Conv RLC: prove `conv_rlc_left == conv_rlc_right` with γ as public input.
pub fn build_conv_rlc_circuit(
    conv: &ConvLayerProofSpec,
    challenge: &ClientChallenge,
) -> Result<MacRlcCircuit, String> {
    let gamma = challenge.gamma_scalar();
    let left = conv_rlc_left(&conv.output_flat, &gamma);
    let right = conv_rlc_right(&conv.filter_flat, &conv.windows, &gamma);

    // Spartan requires num_vars / num_cons powers of two; constant 1 lives at index `num_vars`.
    let num_vars = 4usize;
    let num_inputs = 2usize; // gamma, block tag
    let num_cons = 1usize;
    let num_non_zero = 4usize;

    let one = Scalar::one();
    let minus_one = -one;

    let mut a: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let mut b: Vec<(usize, usize, [u8; 32])> = Vec::new();
    let c: Vec<(usize, usize, [u8; 32])> = Vec::new();

    // (left - right) * 1 = 0
    a.push((0, 0, scalar_bytes(&one)));
    a.push((0, 1, scalar_bytes(&minus_one)));
    b.push((0, num_vars, scalar_bytes(&one)));

    let inst = Instance::new(num_cons, num_vars, num_inputs, &a, &b, &c)
        .map_err(|e| format!("Instance::new: {e:?}"))?;

    let mut vars = vec![Scalar::zero().to_bytes(); inst.inst.get_num_vars()];
    vars[0] = left.to_bytes();
    vars[1] = right.to_bytes();
    let assignment_vars = VarsAssignment::new(&vars).map_err(|e| format!("{e:?}"))?;

    let mut inputs = vec![Scalar::zero().to_bytes(); num_inputs];
    inputs[0] = gamma.to_bytes();
    inputs[1] = Scalar::from(9u64).to_bytes(); // circuit tag: conv eq9
    let assignment_inputs = InputsAssignment::new(&inputs).map_err(|e| format!("{e:?}"))?;

    inst.is_sat(&assignment_vars, &assignment_inputs)
        .map_err(|e| format!("{e:?}"))?
        .then_some(())
        .ok_or_else(|| "mac_rlc conv instance not satisfiable".to_string())?;

    // Spartan pads constraints/variables internally; SNARKGens must use padded sizes.
    Ok(MacRlcCircuit {
        num_cons: inst.inst.get_num_cons(),
        num_vars: inst.inst.get_num_vars(),
        num_inputs: inst.inst.get_num_inputs(),
        num_non_zero,
        inst,
        vars: assignment_vars,
        inputs: assignment_inputs,
    })
}

pub fn build_mac_rlc_circuit(
    stack: &ServerLinearProofStack,
    challenge: &ClientChallenge,
) -> Result<MacRlcCircuit, String> {
    let conv = stack
        .conv
        .as_ref()
        .ok_or_else(|| "mac_rlc requires conv layer".to_string())?;
    build_conv_rlc_circuit(conv, challenge)
}
