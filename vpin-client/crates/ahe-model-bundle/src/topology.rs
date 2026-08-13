#[derive(Clone, Copy, Debug)]
pub struct TruncationPhase {
    pub phase_id: &'static str,
    pub client_action: &'static str,
    pub shift_bits: Option<u32>,
    pub shape: &'static [usize],
}

#[derive(Clone, Copy, Debug)]
pub struct NetworkTopology {
    pub network_id: &'static str,
    pub pool_kernel: usize,
    pub pool_stride: usize,
    pub truncation_phases: &'static [TruncationPhase],
}

pub const NETWORK_A: NetworkTopology = NetworkTopology {
    network_id: "A",
    pool_kernel: 4,
    pool_stride: 4,
    truncation_phases: &[
        TruncationPhase {
            phase_id: "after_conv",
            client_action: "relu",
            shift_bits: None,
            shape: &[1, 1, 32, 32],
        },
        TruncationPhase {
            phase_id: "after_pool",
            client_action: "shift",
            shift_bits: Some(26),
            shape: &[1, 64],
        },
        TruncationPhase {
            phase_id: "after_fc1",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 16],
        },
        TruncationPhase {
            phase_id: "after_fc2",
            client_action: "relu_only",
            shift_bits: None,
            shape: &[1, 10],
        },
    ],
};
