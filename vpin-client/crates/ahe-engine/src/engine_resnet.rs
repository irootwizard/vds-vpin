/// AHE engine for ResNet18/CIFAR-10 — 18-phase protocol.
use ahe_crypto_e2::{CurveE2, E2Point, KeyMaterial};
use ahe_homomorphic::{
    encrypt_resnet_bias_f32, get_op_counters, reset_op_counters, resnet_add_ds_shortcut,
    resnet_add_identity_shortcut, resnet_avgpool_fc, resnet_conv_ciphertext,
};
use ahe_model_bundle::{NetworkTopology, ResNetWeights, TruncationPhase, RESNET18_CIFAR};
use ndarray::{Array1, Array4};
use rand::Rng;
use thiserror::Error;

type Ct4 = Vec<Vec<Vec<Vec<E2Point>>>>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResNetPhase {
    WaitInitial,
    WaitAfterStem,
    WaitAfterL1B0C1,
    WaitAfterL1B0C2,
    WaitAfterL1B1C1,
    WaitAfterL1B1C2,
    WaitAfterL2B0C1,
    WaitAfterL2B0C2,
    WaitAfterL2B1C1,
    WaitAfterL2B1C2,
    WaitAfterL3B0C1,
    WaitAfterL3B0C2,
    WaitAfterL3B1C1,
    WaitAfterL3B1C2,
    WaitAfterL4B0C1,
    WaitAfterL4B0C2,
    WaitAfterL4B1C1,
    WaitAfterL4B1C2,
    Done,
}

#[derive(Clone, Debug)]
pub struct ResNetStepResult {
    pub truncate: Option<TruncateStepResNet>,
    pub output_c1: Option<Ct4>,
    pub output_c2: Option<Ct4>,
    pub inference_complete: bool,
    pub num_pt_add: u64,
    pub num_pt_mult: u64,
}

#[derive(Clone, Debug)]
pub struct TruncateStepResNet {
    pub phase_id: String,
    pub client_action: String,
    pub shift_bits: Option<u32>,
    pub shape: Vec<usize>,
    pub pool_kernel: Option<usize>,
    pub input_shape: Option<Vec<usize>>,
}

#[derive(Error, Debug)]
pub enum ResNetEngineError {
    #[error("invalid phase transition: phase_id={0} engine={1:?}")]
    InvalidTransition(String, ResNetPhase),
    #[error("unexpected phase {0:?}")]
    UnexpectedPhase(ResNetPhase),
}

pub struct AheResNetEngine<R: Rng> {
    pub public_key: E2Point,
    pub weights: ResNetWeights,
    pub topology: NetworkTopology,
    pub phase: ResNetPhase,
    identity: E2Point,
    rng: R,
    ds_c1: Option<Ct4>,
    ds_c2: Option<Ct4>,
    id_c1: Option<Ct4>,
    id_c2: Option<Ct4>,
}

// Free helpers — no self borrow needed, avoiding borrow conflicts with &self.weights + &mut self.rng.

fn make_keys(public_key: &E2Point) -> KeyMaterial {
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

fn ebias<R: Rng>(bias: &Array1<f64>, public_key: &E2Point, rng: &mut R) -> (Vec<E2Point>, Vec<E2Point>) {
    let bias_vec: Vec<f64> = bias.iter().copied().collect();
    let keys = make_keys(public_key);
    encrypt_resnet_bias_f32(
        &bias_vec,
        &keys.generator,
        &keys.public_key,
        &keys.curve_order,
        rng,
    )
}

fn conv<R: Rng>(
    c1: &Ct4,
    c2: &Ct4,
    w: &Array4<f64>,
    b: &Array1<f64>,
    padding: usize,
    stride: usize,
    identity: &E2Point,
    public_key: &E2Point,
    rng: &mut R,
) -> (Ct4, Ct4) {
    let (bc1, bc2) = ebias(b, public_key, rng);
    resnet_conv_ciphertext(c1, c2, w, &bc1, &bc2, identity, padding, stride)
}

impl<R: Rng> AheResNetEngine<R> {
    pub fn new(public_key: E2Point, weights: ResNetWeights, rng: R) -> Self {
        reset_op_counters();
        Self {
            public_key,
            weights,
            topology: RESNET18_CIFAR,
            phase: ResNetPhase::WaitInitial,
            identity: E2Point::Identity,
            rng,
            ds_c1: None,
            ds_c2: None,
            id_c1: None,
            id_c2: None,
        }
    }

    pub fn bind_initial_ciphertext(&mut self, c1: Ct4, c2: Ct4) -> Result<ResNetStepResult, ResNetEngineError> {
        if self.phase != ResNetPhase::WaitInitial {
            return Err(ResNetEngineError::UnexpectedPhase(self.phase));
        }
        let (oc1, oc2) = conv(&c1, &c2, &self.weights.stem_w, &self.weights.stem_b, 1, 1, &self.identity, &self.public_key, &mut self.rng);
        self.phase = ResNetPhase::WaitAfterStem;
        let step = &self.topology.truncation_phases[0];
        Ok(step_result(step, oc1, oc2, false))
    }

    pub fn accept_client_ciphertext(
        &mut self,
        phase_id: &str,
        c1: Ct4,
        c2: Ct4,
    ) -> Result<ResNetStepResult, ResNetEngineError> {
        let w = &self.weights;
        let id = &self.identity;
        let pk = &self.public_key;
        let rng = &mut self.rng;

        let (next_phase, oc1, oc2, complete) = match (phase_id, self.phase) {
            // ── Layer1 Block0 ──
            ("after_stem", ResNetPhase::WaitAfterStem) => {
                self.id_c1 = Some(c1.clone());
                self.id_c2 = Some(c2.clone());
                let o = conv(&c1, &c2, &w.l1b0_conv1_w, &w.l1b0_conv1_b, 1, 1, id, pk, rng);
                (ResNetPhase::WaitAfterL1B0C1, o.0, o.1, false)
            }
            ("after_l1b0c1", ResNetPhase::WaitAfterL1B0C1) => {
                let o = conv(&c1, &c2, &w.l1b0_conv2_w, &w.l1b0_conv2_b, 1, 1, id, pk, rng);
                let id1 = self.id_c1.take().unwrap();
                let id2 = self.id_c2.take().unwrap();
                let o = resnet_add_identity_shortcut(&o.0, &o.1, &id1, &id2);
                (ResNetPhase::WaitAfterL1B0C2, o.0, o.1, false)
            }
            // ── Layer1 Block1 ──
            ("after_l1b0c2", ResNetPhase::WaitAfterL1B0C2) => {
                self.id_c1 = Some(c1.clone());
                self.id_c2 = Some(c2.clone());
                let o = conv(&c1, &c2, &w.l1b1_conv1_w, &w.l1b1_conv1_b, 1, 1, id, pk, rng);
                (ResNetPhase::WaitAfterL1B1C1, o.0, o.1, false)
            }
            ("after_l1b1c1", ResNetPhase::WaitAfterL1B1C1) => {
                let o = conv(&c1, &c2, &w.l1b1_conv2_w, &w.l1b1_conv2_b, 1, 1, id, pk, rng);
                let id1 = self.id_c1.take().unwrap();
                let id2 = self.id_c2.take().unwrap();
                let o = resnet_add_identity_shortcut(&o.0, &o.1, &id1, &id2);
                (ResNetPhase::WaitAfterL1B1C2, o.0, o.1, false)
            }
            // ── Layer2 Block0 (downsample) ──
            ("after_l1b1c2", ResNetPhase::WaitAfterL1B1C2) => {
                let ds = conv(&c1, &c2, &w.l2b0_ds_w, &w.l2b0_ds_b, 0, 2, id, pk, rng);
                self.ds_c1 = Some(ds.0);
                self.ds_c2 = Some(ds.1);
                let o = conv(&c1, &c2, &w.l2b0_conv1_w, &w.l2b0_conv1_b, 1, 2, id, pk, rng);
                (ResNetPhase::WaitAfterL2B0C1, o.0, o.1, false)
            }
            ("after_l2b0c1", ResNetPhase::WaitAfterL2B0C1) => {
                let o = conv(&c1, &c2, &w.l2b0_conv2_w, &w.l2b0_conv2_b, 1, 1, id, pk, rng);
                let ds1 = self.ds_c1.take().unwrap();
                let ds2 = self.ds_c2.take().unwrap();
                let o = resnet_add_ds_shortcut(&o.0, &o.1, &ds1, &ds2);
                (ResNetPhase::WaitAfterL2B0C2, o.0, o.1, false)
            }
            // ── Layer2 Block1 ──
            ("after_l2b0c2", ResNetPhase::WaitAfterL2B0C2) => {
                self.id_c1 = Some(c1.clone());
                self.id_c2 = Some(c2.clone());
                let o = conv(&c1, &c2, &w.l2b1_conv1_w, &w.l2b1_conv1_b, 1, 1, id, pk, rng);
                (ResNetPhase::WaitAfterL2B1C1, o.0, o.1, false)
            }
            ("after_l2b1c1", ResNetPhase::WaitAfterL2B1C1) => {
                let o = conv(&c1, &c2, &w.l2b1_conv2_w, &w.l2b1_conv2_b, 1, 1, id, pk, rng);
                let id1 = self.id_c1.take().unwrap();
                let id2 = self.id_c2.take().unwrap();
                let o = resnet_add_identity_shortcut(&o.0, &o.1, &id1, &id2);
                (ResNetPhase::WaitAfterL2B1C2, o.0, o.1, false)
            }
            // ── Layer3 Block0 (downsample) ──
            ("after_l2b1c2", ResNetPhase::WaitAfterL2B1C2) => {
                let ds = conv(&c1, &c2, &w.l3b0_ds_w, &w.l3b0_ds_b, 0, 2, id, pk, rng);
                self.ds_c1 = Some(ds.0);
                self.ds_c2 = Some(ds.1);
                let o = conv(&c1, &c2, &w.l3b0_conv1_w, &w.l3b0_conv1_b, 1, 2, id, pk, rng);
                (ResNetPhase::WaitAfterL3B0C1, o.0, o.1, false)
            }
            ("after_l3b0c1", ResNetPhase::WaitAfterL3B0C1) => {
                let o = conv(&c1, &c2, &w.l3b0_conv2_w, &w.l3b0_conv2_b, 1, 1, id, pk, rng);
                let ds1 = self.ds_c1.take().unwrap();
                let ds2 = self.ds_c2.take().unwrap();
                let o = resnet_add_ds_shortcut(&o.0, &o.1, &ds1, &ds2);
                (ResNetPhase::WaitAfterL3B0C2, o.0, o.1, false)
            }
            // ── Layer3 Block1 ──
            ("after_l3b0c2", ResNetPhase::WaitAfterL3B0C2) => {
                self.id_c1 = Some(c1.clone());
                self.id_c2 = Some(c2.clone());
                let o = conv(&c1, &c2, &w.l3b1_conv1_w, &w.l3b1_conv1_b, 1, 1, id, pk, rng);
                (ResNetPhase::WaitAfterL3B1C1, o.0, o.1, false)
            }
            ("after_l3b1c1", ResNetPhase::WaitAfterL3B1C1) => {
                let o = conv(&c1, &c2, &w.l3b1_conv2_w, &w.l3b1_conv2_b, 1, 1, id, pk, rng);
                let id1 = self.id_c1.take().unwrap();
                let id2 = self.id_c2.take().unwrap();
                let o = resnet_add_identity_shortcut(&o.0, &o.1, &id1, &id2);
                (ResNetPhase::WaitAfterL3B1C2, o.0, o.1, false)
            }
            // ── Layer4 Block0 (downsample) ──
            ("after_l3b1c2", ResNetPhase::WaitAfterL3B1C2) => {
                let ds = conv(&c1, &c2, &w.l4b0_ds_w, &w.l4b0_ds_b, 0, 2, id, pk, rng);
                self.ds_c1 = Some(ds.0);
                self.ds_c2 = Some(ds.1);
                let o = conv(&c1, &c2, &w.l4b0_conv1_w, &w.l4b0_conv1_b, 1, 2, id, pk, rng);
                (ResNetPhase::WaitAfterL4B0C1, o.0, o.1, false)
            }
            ("after_l4b0c1", ResNetPhase::WaitAfterL4B0C1) => {
                let o = conv(&c1, &c2, &w.l4b0_conv2_w, &w.l4b0_conv2_b, 1, 1, id, pk, rng);
                let ds1 = self.ds_c1.take().unwrap();
                let ds2 = self.ds_c2.take().unwrap();
                let o = resnet_add_ds_shortcut(&o.0, &o.1, &ds1, &ds2);
                (ResNetPhase::WaitAfterL4B0C2, o.0, o.1, false)
            }
            // ── Layer4 Block1 ──
            ("after_l4b0c2", ResNetPhase::WaitAfterL4B0C2) => {
                self.id_c1 = Some(c1.clone());
                self.id_c2 = Some(c2.clone());
                let o = conv(&c1, &c2, &w.l4b1_conv1_w, &w.l4b1_conv1_b, 1, 1, id, pk, rng);
                (ResNetPhase::WaitAfterL4B1C1, o.0, o.1, false)
            }
            ("after_l4b1c1", ResNetPhase::WaitAfterL4B1C1) => {
                let o = conv(&c1, &c2, &w.l4b1_conv2_w, &w.l4b1_conv2_b, 1, 1, id, pk, rng);
                let id1 = self.id_c1.take().unwrap();
                let id2 = self.id_c2.take().unwrap();
                let o = resnet_add_identity_shortcut(&o.0, &o.1, &id1, &id2);
                (ResNetPhase::WaitAfterL4B1C2, o.0, o.1, false)
            }
            // ── AvgPool + Linear ──
            ("after_l4b1c2", ResNetPhase::WaitAfterL4B1C2) => {
                let keys = make_keys(pk);
                let (logits1, logits2) = resnet_avgpool_fc(
                    &c1, &c2, &w.linear_w, &w.linear_b, &keys, rng,
                );
                // logits are [1, 10] (2-D); wrap to [1, 10, 1, 1] Ct4 so client can decrypt
                let oc1: Ct4 = vec![
                    logits1[0].iter().map(|p| vec![vec![p.clone()]]).collect::<Vec<_>>()
                ];
                let oc2: Ct4 = vec![
                    logits2[0].iter().map(|p| vec![vec![p.clone()]]).collect::<Vec<_>>()
                ];
                self.phase = ResNetPhase::Done;
                let step = &self.topology.truncation_phases[17];
                let (add, mult) = get_op_counters();
                let trunc = TruncateStepResNet {
                    phase_id: step.phase_id.to_string(),
                    client_action: step.client_action.to_string(),
                    shift_bits: step.shift_bits,
                    shape: vec![1, 10],  // logits_only shape is [1, 10]
                    pool_kernel: step.pool_kernel,
                    input_shape: step.input_shape.map(|s| s.to_vec()),
                };
                return Ok(ResNetStepResult {
                    truncate: Some(trunc),
                    output_c1: Some(oc1),
                    output_c2: Some(oc2),
                    inference_complete: true,
                    num_pt_add: add,
                    num_pt_mult: mult,
                });
            }
            _ => return Err(ResNetEngineError::InvalidTransition(phase_id.into(), self.phase)),
        };

        self.phase = next_phase;
        let phase_idx = match next_phase {
            ResNetPhase::WaitAfterL1B0C1 => 1,
            ResNetPhase::WaitAfterL1B0C2 => 2,
            ResNetPhase::WaitAfterL1B1C1 => 3,
            ResNetPhase::WaitAfterL1B1C2 => 4,
            ResNetPhase::WaitAfterL2B0C1 => 5,
            ResNetPhase::WaitAfterL2B0C2 => 6,
            ResNetPhase::WaitAfterL2B1C1 => 7,
            ResNetPhase::WaitAfterL2B1C2 => 8,
            ResNetPhase::WaitAfterL3B0C1 => 9,
            ResNetPhase::WaitAfterL3B0C2 => 10,
            ResNetPhase::WaitAfterL3B1C1 => 11,
            ResNetPhase::WaitAfterL3B1C2 => 12,
            ResNetPhase::WaitAfterL4B0C1 => 13,
            ResNetPhase::WaitAfterL4B0C2 => 14,
            ResNetPhase::WaitAfterL4B1C1 => 15,
            ResNetPhase::WaitAfterL4B1C2 => 16,
            _ => unreachable!(),
        };
        let step = &self.topology.truncation_phases[phase_idx];
        Ok(step_result(step, oc1, oc2, complete))
    }
}

fn step_result(step: &TruncationPhase, c1: Ct4, c2: Ct4, complete: bool) -> ResNetStepResult {
    let (add, mult) = get_op_counters();
    let trunc = TruncateStepResNet {
        phase_id: step.phase_id.to_string(),
        client_action: step.client_action.to_string(),
        shift_bits: step.shift_bits,
        shape: step.shape.to_vec(),
        pool_kernel: step.pool_kernel,
        input_shape: step.input_shape.map(|s| s.to_vec()),
    };
    ResNetStepResult {
        truncate: Some(trunc),
        output_c1: Some(c1),
        output_c2: Some(c2),
        inference_complete: complete,
        num_pt_add: add,
        num_pt_mult: mult,
    }
}
