use ahe_codec_ec::{ec_grid2_to_ark, EcE2Point, EcKeyMaterial};
use ahe_crypto_e2_ec::wire_generator;
use ahe_homomorphic::{
    avg_pool_ciphertext_ec, conv2_ciphertext_ec, fc1_layer_ec, fc2_layer_ec,
    flatten_ciphertext_ec, get_ec_op_counters, reset_ec_op_counters,
};
use ahe_model_bundle::{NetworkAWeights, NetworkTopology, TruncationPhase, NETWORK_A};
use num_bigint::BigUint;
use rand::Rng;

pub use crate::engine::{EngineError, EnginePhase, EngineStepResult, TruncateStep};

pub type CtTensor4Ec = Vec<Vec<Vec<Vec<EcE2Point>>>>;

pub struct AheEngineEc<R: Rng> {
    pub public_key: EcE2Point,
    pub weights: NetworkAWeights,
    pub topology: NetworkTopology,
    pub phase: EnginePhase,
    identity: EcE2Point,
    pool_kernel: usize,
    pool_stride: usize,
    rng: R,
}

impl<R: Rng> AheEngineEc<R> {
    pub fn new(public_key: EcE2Point, weights: NetworkAWeights, rng: R) -> Self {
        reset_ec_op_counters();
        Self {
            public_key,
            weights,
            topology: NETWORK_A,
            phase: EnginePhase::WaitInitial,
            identity: EcE2Point::Identity,
            pool_kernel: NETWORK_A.pool_kernel,
            pool_stride: NETWORK_A.pool_stride,
            rng,
        }
    }

    pub fn bind_initial_ciphertext(
        &mut self,
        c1: CtTensor4Ec,
        c2: CtTensor4Ec,
    ) -> Result<EngineStepResult, EngineError> {
        if self.phase != EnginePhase::WaitInitial {
            return Err(EngineError::UnexpectedPhase(self.phase));
        }
        let (out_c1, out_c2) = conv2_ciphertext_ec(&c1, &c2, &self.identity);
        self.phase = EnginePhase::WaitAfterConv;
        let step = &self.topology.truncation_phases[0];
        Ok(step_result_ec(step, Some(out_c1), Some(out_c2), None, None, false))
    }

    pub fn accept_client_ciphertext(
        &mut self,
        phase_id: &str,
        c1: CtTensor4Ec,
        c2: CtTensor4Ec,
        c1_2d: Option<Vec<Vec<EcE2Point>>>,
        c2_2d: Option<Vec<Vec<EcE2Point>>>,
    ) -> Result<EngineStepResult, EngineError> {
        match (phase_id, self.phase) {
            ("after_conv", EnginePhase::WaitAfterConv) => {
                let (pool_c1, pool_c2) = avg_pool_ciphertext_ec(
                    &c1,
                    &c2,
                    &self.identity,
                    self.pool_kernel,
                    self.pool_stride,
                );
                let (flat_c1, flat_c2) = flatten_ciphertext_ec(&pool_c1, &pool_c2);
                self.phase = EnginePhase::WaitAfterPool;
                let step = &self.topology.truncation_phases[1];
                Ok(step_result_ec(
                    step,
                    None,
                    None,
                    Some(flat_c1),
                    Some(flat_c2),
                    false,
                ))
            }
            ("after_pool", EnginePhase::WaitAfterPool) => {
                let in1 = c1_2d.ok_or_else(|| {
                    EngineError::InvalidTransition(phase_id.into(), self.phase)
                })?;
                let in2 = c2_2d.ok_or_else(|| {
                    EngineError::InvalidTransition(phase_id.into(), self.phase)
                })?;
                let keys = engine_keys_ec(&self.public_key);
                let (out_c1, out_c2) =
                    fc1_layer_ec(&self.weights, &in1, &in2, &keys, &mut self.rng);
                self.phase = EnginePhase::WaitAfterFc1;
                let step = &self.topology.truncation_phases[2];
                Ok(step_result_ec(
                    step,
                    None,
                    None,
                    Some(out_c1),
                    Some(out_c2),
                    false,
                ))
            }
            ("after_fc1", EnginePhase::WaitAfterFc1) => {
                let in1 = c1_2d.ok_or_else(|| {
                    EngineError::InvalidTransition(phase_id.into(), self.phase)
                })?;
                let in2 = c2_2d.ok_or_else(|| {
                    EngineError::InvalidTransition(phase_id.into(), self.phase)
                })?;
                let keys = engine_keys_ec(&self.public_key);
                let (out_c1, out_c2) =
                    fc2_layer_ec(&self.weights, &in1, &in2, &keys, &mut self.rng);
                self.phase = EnginePhase::Done;
                let step = &self.topology.truncation_phases[3];
                let (add, mult) = get_ec_op_counters();
                Ok(EngineStepResult {
                    truncate: Some(truncate_from_ec(step)),
                    output_c1: None,
                    output_c2: None,
                    output_c1_2d: Some(ec_grid2_to_ark(out_c1)),
                    output_c2_2d: Some(ec_grid2_to_ark(out_c2)),
                    inference_complete: true,
                    num_pt_add: add,
                    num_pt_mult: mult,
                })
            }
            _ => Err(EngineError::InvalidTransition(phase_id.into(), self.phase)),
        }
    }
}

fn engine_keys_ec(public_key: &EcE2Point) -> EcKeyMaterial {
    let mut keys = EcKeyMaterial::key_gen_deterministic(BigUint::from(1u32));
    keys.public_key = public_key.clone();
    keys.generator = wire_generator();
    keys
}

fn truncate_from_ec(step: &TruncationPhase) -> TruncateStep {
    TruncateStep {
        phase_id: step.phase_id.to_string(),
        client_action: step.client_action.to_string(),
        shift_bits: step.shift_bits,
        shape: step.shape.to_vec(),
    }
}

fn step_result_ec(
    step: &TruncationPhase,
    o1: Option<CtTensor4Ec>,
    o2: Option<CtTensor4Ec>,
    o1_2d: Option<Vec<Vec<EcE2Point>>>,
    o2_2d: Option<Vec<Vec<EcE2Point>>>,
    complete: bool,
) -> EngineStepResult {
    use ahe_codec_ec::{ec_grid2_to_ark, ec_tensor4_to_ark};
    let (add, mult) = get_ec_op_counters();
    EngineStepResult {
        truncate: Some(truncate_from_ec(step)),
        output_c1: o1.map(ec_tensor4_to_ark),
        output_c2: o2.map(ec_tensor4_to_ark),
        output_c1_2d: o1_2d.map(ec_grid2_to_ark),
        output_c2_2d: o2_2d.map(ec_grid2_to_ark),
        inference_complete: complete,
        num_pt_add: add,
        num_pt_mult: mult,
    }
}
