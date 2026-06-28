use ahe_crypto_e2::{CurveE2, E2Point, KeyMaterial};
use ahe_homomorphic::{
    avg_pool_ciphertext, conv2_ciphertext, fc1_layer, fc2_layer, flatten_ciphertext,
    get_op_counters, reset_op_counters,
};
use ahe_model_bundle::{NetworkAWeights, NetworkTopology, TruncationPhase, NETWORK_A};
use rand::Rng;
use thiserror::Error;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EnginePhase {
    WaitInitial,
    WaitAfterConv,
    WaitAfterPool,
    WaitAfterFc1,
    Done,
}

#[derive(Clone, Debug)]
pub struct TruncateStep {
    pub phase_id: String,
    pub client_action: String,
    pub shift_bits: Option<u32>,
    pub shape: Vec<usize>,
}

#[derive(Clone, Debug)]
pub struct EngineStepResult {
    pub truncate: Option<TruncateStep>,
    pub output_c1: Option<CtTensor4>,
    pub output_c2: Option<CtTensor4>,
    pub output_c1_2d: Option<Vec<Vec<E2Point>>>,
    pub output_c2_2d: Option<Vec<Vec<E2Point>>>,
    pub inference_complete: bool,
    pub num_pt_add: u64,
    pub num_pt_mult: u64,
}

pub type CtTensor4 = Vec<Vec<Vec<Vec<E2Point>>>>;

#[derive(Error, Debug)]
pub enum EngineError {
    #[error("invalid phase transition: phase_id={0} engine={1:?}")]
    InvalidTransition(String, EnginePhase),
    #[error("unexpected phase {0:?}")]
    UnexpectedPhase(EnginePhase),
}

pub struct AheEngine<R: Rng> {
    pub public_key: E2Point,
    pub weights: NetworkAWeights,
    pub topology: NetworkTopology,
    pub phase: EnginePhase,
    identity: E2Point,
    pool_kernel: usize,
    pool_stride: usize,
    rng: R,
}

impl<R: Rng> AheEngine<R> {
    pub fn new(public_key: E2Point, weights: NetworkAWeights, rng: R) -> Self {
        reset_op_counters();
        Self {
            public_key,
            weights,
            topology: NETWORK_A,
            phase: EnginePhase::WaitInitial,
            identity: E2Point::Identity,
            pool_kernel: NETWORK_A.pool_kernel,
            pool_stride: NETWORK_A.pool_stride,
            rng,
        }
    }

    pub fn bind_initial_ciphertext(
        &mut self,
        c1: CtTensor4,
        c2: CtTensor4,
    ) -> Result<EngineStepResult, EngineError> {
        if self.phase != EnginePhase::WaitInitial {
            return Err(EngineError::UnexpectedPhase(self.phase));
        }
        let (out_c1, out_c2) = conv2_ciphertext(&c1, &c2, &self.identity);
        self.phase = EnginePhase::WaitAfterConv;
        let step = &self.topology.truncation_phases[0];
        Ok(step_result(step, Some(out_c1), Some(out_c2), None, None, false))
    }

    pub fn accept_client_ciphertext(
        &mut self,
        phase_id: &str,
        c1: CtTensor4,
        c2: CtTensor4,
        c1_2d: Option<Vec<Vec<E2Point>>>,
        c2_2d: Option<Vec<Vec<E2Point>>>,
    ) -> Result<EngineStepResult, EngineError> {
        match (phase_id, self.phase) {
            ("after_conv", EnginePhase::WaitAfterConv) => {
                let (pool_c1, pool_c2) = avg_pool_ciphertext(
                    &c1,
                    &c2,
                    &self.identity,
                    self.pool_kernel,
                    self.pool_stride,
                );
                let (flat_c1, flat_c2) = flatten_ciphertext(&pool_c1, &pool_c2);
                self.phase = EnginePhase::WaitAfterPool;
                let step = &self.topology.truncation_phases[1];
                Ok(step_result(
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
                let keys = engine_keys(&self.public_key);
                let (out_c1, out_c2) = fc1_layer(&self.weights, &in1, &in2, &keys, &mut self.rng);
                self.phase = EnginePhase::WaitAfterFc1;
                let step = &self.topology.truncation_phases[2];
                Ok(step_result(
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
                let keys = engine_keys(&self.public_key);
                let (out_c1, out_c2) = fc2_layer(&self.weights, &in1, &in2, &keys, &mut self.rng);
                self.phase = EnginePhase::Done;
                let step = &self.topology.truncation_phases[3];
                let (add, mult) = get_op_counters();
                Ok(EngineStepResult {
                    truncate: Some(truncate_from(step)),
                    output_c1: None,
                    output_c2: None,
                    output_c1_2d: Some(out_c1),
                    output_c2_2d: Some(out_c2),
                    inference_complete: true,
                    num_pt_add: add,
                    num_pt_mult: mult,
                })
            }
            _ => Err(EngineError::InvalidTransition(phase_id.into(), self.phase)),
        }
    }
}

fn engine_keys(public_key: &E2Point) -> KeyMaterial {
    let g_aff = CurveE2::generator();
    let g = E2Point::Affine {
        x: CurveE2::coord_x_be(&g_aff).expect("gx"),
        y: CurveE2::coord_y_be(&g_aff).expect("gy"),
    };
    KeyMaterial {
        private_scalar: 1u32.into(),
        public_key: public_key.clone(),
        generator: g,
        curve_order: CurveE2::order(),
    }
}

fn truncate_from(step: &TruncationPhase) -> TruncateStep {
    TruncateStep {
        phase_id: step.phase_id.to_string(),
        client_action: step.client_action.to_string(),
        shift_bits: step.shift_bits,
        shape: step.shape.to_vec(),
    }
}

fn step_result(
    step: &TruncationPhase,
    o1: Option<CtTensor4>,
    o2: Option<CtTensor4>,
    o1_2d: Option<Vec<Vec<E2Point>>>,
    o2_2d: Option<Vec<Vec<E2Point>>>,
    complete: bool,
) -> EngineStepResult {
    let (add, mult) = get_op_counters();
    EngineStepResult {
        truncate: Some(truncate_from(step)),
        output_c1: o1,
        output_c2: o2,
        output_c1_2d: o1_2d,
        output_c2_2d: o2_2d,
        inference_complete: complete,
        num_pt_add: add,
        num_pt_mult: mult,
    }
}
