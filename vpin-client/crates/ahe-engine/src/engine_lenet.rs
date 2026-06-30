/// AHE engine for LeNet inference (both MNIST and CIFAR-10 variants).
///
/// Phase sequence:
///   WaitInitial     — bind initial ciphertext → run conv1 → send after_conv1
///   WaitAfterConv1  — receive relu+pool+shift re-enc → run conv2 → send after_conv2
///   WaitAfterConv2  — receive relu+pool+shift re-enc → flatten → run c3 → send after_c3
///   WaitAfterC3     — receive relu+shift re-enc → run fc4 → send after_fc4
///   WaitAfterFc4    — receive relu+shift re-enc → run fc5 → send after_fc5 (done)
///   Done
///
/// The server sends 4D ciphertext for conv phases and 2D for FC phases.
/// The client sends 4D re-encryption after conv1/conv2 (pool reduces spatial dims),
/// and 2D for c3/fc4.
use ahe_crypto_e2::{CurveE2, E2Point, KeyMaterial};
use ahe_homomorphic::{
    get_op_counters, lenet_flatten, reset_op_counters,
};
use ahe_model_bundle::{NetworkTopology, TruncationPhase};
use rand::Rng;
use thiserror::Error;

type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LeNetPhase {
    WaitInitial,
    WaitAfterConv1,
    WaitAfterConv2,
    WaitAfterC3,
    WaitAfterFc4,
    Done,
}

/// Enum over the two possible weight types, selected at construction time.
pub enum LeNetWeights {
    Mnist(ahe_model_bundle::LeNetMnistWeights),
    Cifar(ahe_model_bundle::LeNetCifarWeights),
}

#[derive(Clone, Debug)]
pub struct TruncateStepLenet {
    pub phase_id: String,
    pub client_action: String,
    pub shift_bits: Option<u32>,
    pub shape: Vec<usize>,
    pub pool_kernel: Option<usize>,
    pub input_shape: Option<Vec<usize>>,
}

#[derive(Debug)]
pub struct LeNetStepResult {
    pub truncate: Option<TruncateStepLenet>,
    pub output_c1: Option<Ct4>,
    pub output_c2: Option<Ct4>,
    pub output_c1_2d: Option<Vec<Vec<E2Point>>>,
    pub output_c2_2d: Option<Vec<Vec<E2Point>>>,
    pub inference_complete: bool,
    pub num_pt_add: u64,
    pub num_pt_mult: u64,
}

#[derive(Error, Debug)]
pub enum LeNetEngineError {
    #[error("invalid phase transition: phase_id={0} engine={1:?}")]
    InvalidTransition(String, LeNetPhase),
    #[error("unexpected phase {0:?}")]
    UnexpectedPhase(LeNetPhase),
}

pub struct AheLeNetEngine<R: Rng> {
    pub public_key: E2Point,
    pub weights: LeNetWeights,
    pub topology: NetworkTopology,
    pub phase: LeNetPhase,
    identity: E2Point,
    rng: R,
}

impl<R: Rng> AheLeNetEngine<R> {
    pub fn new_mnist(
        public_key: E2Point,
        weights: ahe_model_bundle::LeNetMnistWeights,
        topology: NetworkTopology,
        rng: R,
    ) -> Self {
        reset_op_counters();
        Self {
            public_key,
            weights: LeNetWeights::Mnist(weights),
            topology,
            phase: LeNetPhase::WaitInitial,
            identity: E2Point::Identity,
            rng,
        }
    }

    pub fn new_cifar(
        public_key: E2Point,
        weights: ahe_model_bundle::LeNetCifarWeights,
        topology: NetworkTopology,
        rng: R,
    ) -> Self {
        reset_op_counters();
        Self {
            public_key,
            weights: LeNetWeights::Cifar(weights),
            topology,
            phase: LeNetPhase::WaitInitial,
            identity: E2Point::Identity,
            rng,
        }
    }

    pub fn bind_initial_ciphertext(
        &mut self,
        c1: Ct4,
        c2: Ct4,
    ) -> Result<LeNetStepResult, LeNetEngineError> {
        if self.phase != LeNetPhase::WaitInitial {
            return Err(LeNetEngineError::UnexpectedPhase(self.phase));
        }
        let keys = self.keys();
        let (out_c1, out_c2) = match &self.weights {
            LeNetWeights::Mnist(w) => ahe_homomorphic::lenet_mnist_conv1(
                w, &c1, &c2, &keys, &mut self.rng, &self.identity,
            ),
            LeNetWeights::Cifar(w) => ahe_homomorphic::lenet_cifar_conv1(
                w, &c1, &c2, &keys, &mut self.rng, &self.identity,
            ),
        };
        self.phase = LeNetPhase::WaitAfterConv1;
        let step = &self.topology.truncation_phases[0]; // after_conv1
        Ok(self.step_result_4d(step, out_c1, out_c2, false))
    }

    pub fn accept_client_ciphertext(
        &mut self,
        phase_id: &str,
        c1: Ct4,
        c2: Ct4,
        c1_2d: Option<Vec<Vec<E2Point>>>,
        c2_2d: Option<Vec<Vec<E2Point>>>,
    ) -> Result<LeNetStepResult, LeNetEngineError> {
        let keys = self.keys();
        match (phase_id, self.phase) {
            ("after_conv1", LeNetPhase::WaitAfterConv1) => {
                // c1/c2 is [1, 6, 14, 14] after client relu+pool+shift
                let (out_c1, out_c2) = match &self.weights {
                    LeNetWeights::Mnist(w) => ahe_homomorphic::lenet_mnist_conv2(
                        w, &c1, &c2, &keys, &mut self.rng, &self.identity,
                    ),
                    LeNetWeights::Cifar(w) => ahe_homomorphic::lenet_cifar_conv2(
                        w, &c1, &c2, &keys, &mut self.rng, &self.identity,
                    ),
                };
                self.phase = LeNetPhase::WaitAfterConv2;
                let step = &self.topology.truncation_phases[1]; // after_conv2
                Ok(self.step_result_4d(step, out_c1, out_c2, false))
            }
            ("after_conv2", LeNetPhase::WaitAfterConv2) => {
                // c1/c2 is [1, 16, 5, 5] after client relu+pool+shift; flatten → run c3
                let (flat_c1, flat_c2) = lenet_flatten(&c1, &c2);
                let (out_c1, out_c2) = match &self.weights {
                    LeNetWeights::Mnist(w) => {
                        ahe_homomorphic::lenet_mnist_c3(w, &flat_c1, &flat_c2, &keys, &mut self.rng)
                    }
                    LeNetWeights::Cifar(w) => {
                        ahe_homomorphic::lenet_cifar_c3(w, &flat_c1, &flat_c2, &keys, &mut self.rng)
                    }
                };
                self.phase = LeNetPhase::WaitAfterC3;
                let step = &self.topology.truncation_phases[2]; // after_c3
                Ok(self.step_result_2d(step, out_c1, out_c2, false))
            }
            ("after_c3", LeNetPhase::WaitAfterC3) => {
                let in1 = c1_2d.ok_or_else(|| LeNetEngineError::InvalidTransition(phase_id.into(), self.phase))?;
                let in2 = c2_2d.ok_or_else(|| LeNetEngineError::InvalidTransition(phase_id.into(), self.phase))?;
                let (out_c1, out_c2) = match &self.weights {
                    LeNetWeights::Mnist(w) => {
                        ahe_homomorphic::lenet_mnist_fc4(w, &in1, &in2, &keys, &mut self.rng)
                    }
                    LeNetWeights::Cifar(w) => {
                        ahe_homomorphic::lenet_cifar_fc4(w, &in1, &in2, &keys, &mut self.rng)
                    }
                };
                self.phase = LeNetPhase::WaitAfterFc4;
                let step = &self.topology.truncation_phases[3]; // after_fc4
                Ok(self.step_result_2d(step, out_c1, out_c2, false))
            }
            ("after_fc4", LeNetPhase::WaitAfterFc4) => {
                let in1 = c1_2d.ok_or_else(|| LeNetEngineError::InvalidTransition(phase_id.into(), self.phase))?;
                let in2 = c2_2d.ok_or_else(|| LeNetEngineError::InvalidTransition(phase_id.into(), self.phase))?;
                let (out_c1, out_c2) = match &self.weights {
                    LeNetWeights::Mnist(w) => {
                        ahe_homomorphic::lenet_mnist_fc5(w, &in1, &in2, &keys, &mut self.rng)
                    }
                    LeNetWeights::Cifar(w) => {
                        ahe_homomorphic::lenet_cifar_fc5(w, &in1, &in2, &keys, &mut self.rng)
                    }
                };
                self.phase = LeNetPhase::Done;
                let step = &self.topology.truncation_phases[4]; // after_fc5
                let (add, mult) = get_op_counters();
                let trunc = truncate_from_lenet(step);
                Ok(LeNetStepResult {
                    truncate: Some(trunc),
                    output_c1: None,
                    output_c2: None,
                    output_c1_2d: Some(out_c1),
                    output_c2_2d: Some(out_c2),
                    inference_complete: true,
                    num_pt_add: add,
                    num_pt_mult: mult,
                })
            }
            _ => Err(LeNetEngineError::InvalidTransition(phase_id.into(), self.phase)),
        }
    }

    fn keys(&self) -> KeyMaterial {
        let g_aff = CurveE2::generator();
        let g = E2Point::Affine {
            x: CurveE2::coord_x_be(&g_aff).expect("gx"),
            y: CurveE2::coord_y_be(&g_aff).expect("gy"),
        };
        KeyMaterial {
            private_scalar: 1u32.into(),
            public_key: self.public_key.clone(),
            generator: g,
            curve_order: CurveE2::order(),
        }
    }

    fn step_result_4d(
        &self,
        step: &TruncationPhase,
        c1: Ct4,
        c2: Ct4,
        complete: bool,
    ) -> LeNetStepResult {
        let (add, mult) = get_op_counters();
        LeNetStepResult {
            truncate: Some(truncate_from_lenet(step)),
            output_c1: Some(c1),
            output_c2: Some(c2),
            output_c1_2d: None,
            output_c2_2d: None,
            inference_complete: complete,
            num_pt_add: add,
            num_pt_mult: mult,
        }
    }

    fn step_result_2d(
        &self,
        step: &TruncationPhase,
        c1: Vec<Vec<E2Point>>,
        c2: Vec<Vec<E2Point>>,
        complete: bool,
    ) -> LeNetStepResult {
        let (add, mult) = get_op_counters();
        LeNetStepResult {
            truncate: Some(truncate_from_lenet(step)),
            output_c1: None,
            output_c2: None,
            output_c1_2d: Some(c1),
            output_c2_2d: Some(c2),
            inference_complete: complete,
            num_pt_add: add,
            num_pt_mult: mult,
        }
    }
}

fn truncate_from_lenet(step: &TruncationPhase) -> TruncateStepLenet {
    TruncateStepLenet {
        phase_id: step.phase_id.to_string(),
        client_action: step.client_action.to_string(),
        shift_bits: step.shift_bits,
        shape: step.shape.to_vec(),
        pool_kernel: step.pool_kernel,
        input_shape: step.input_shape.map(|s| s.to_vec()),
    }
}
