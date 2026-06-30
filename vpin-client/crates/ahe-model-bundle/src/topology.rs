#[derive(Clone, Copy, Debug)]
pub struct TruncationPhase {
    pub phase_id: &'static str,
    pub client_action: &'static str,
    pub shift_bits: Option<u32>,
    pub shape: &'static [usize],
    /// Non-None for `relu_pool_shift`: spatial size of the average pool (e.g. 2 for 2×2).
    pub pool_kernel: Option<usize>,
    /// Non-None for `relu_pool_shift`: 4-D input shape [B,C,H,W] before pooling.
    pub input_shape: Option<&'static [usize]>,
}

#[derive(Clone, Copy, Debug)]
pub struct NetworkTopology {
    pub network_id: &'static str,
    /// Server-side pool kernel (Network A only; 0 if pool is client-side).
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
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_pool",
            client_action: "shift",
            shift_bits: Some(26),
            shape: &[1, 64],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc1",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 16],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc2",
            client_action: "relu_only",
            shift_bits: None,
            shape: &[1, 10],
            pool_kernel: None,
            input_shape: None,
        },
    ],
};

// ---------------------------------------------------------------------------
// LeNet MNIST topology  (1×32×32 input, 5 client rounds, pool on client side)
// ---------------------------------------------------------------------------
pub const LENET_MNIST: NetworkTopology = NetworkTopology {
    network_id: "lenet_mnist",
    pool_kernel: 0,   // pool is client-side; no server-side pool
    pool_stride: 0,
    truncation_phases: &[
        TruncationPhase {
            phase_id: "after_conv1",
            client_action: "relu_pool_shift",
            shift_bits: Some(32),
            shape: &[1, 6, 14, 14],        // output shape after relu+pool
            pool_kernel: Some(2),
            input_shape: Some(&[1, 6, 28, 28]),  // shape sent by server
        },
        TruncationPhase {
            phase_id: "after_conv2",
            client_action: "relu_pool_shift",
            shift_bits: Some(32),
            shape: &[1, 16, 5, 5],
            pool_kernel: Some(2),
            input_shape: Some(&[1, 16, 10, 10]),
        },
        TruncationPhase {
            phase_id: "after_c3",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 120],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc4",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 84],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc5",
            client_action: "logits_only",
            shift_bits: None,
            shape: &[1, 10],
            pool_kernel: None,
            input_shape: None,
        },
    ],
};

// ---------------------------------------------------------------------------
// LeNet CIFAR-10 topology  (3×32×32 input, same phase structure as MNIST)
// ---------------------------------------------------------------------------
pub const LENET_CIFAR: NetworkTopology = NetworkTopology {
    network_id: "lenet_cifar",
    pool_kernel: 0,
    pool_stride: 0,
    truncation_phases: &[
        TruncationPhase {
            phase_id: "after_conv1",
            client_action: "relu_pool_shift",
            shift_bits: Some(32),
            shape: &[1, 6, 14, 14],
            pool_kernel: Some(2),
            input_shape: Some(&[1, 6, 28, 28]),
        },
        TruncationPhase {
            phase_id: "after_conv2",
            client_action: "relu_pool_shift",
            shift_bits: Some(32),
            shape: &[1, 16, 5, 5],
            pool_kernel: Some(2),
            input_shape: Some(&[1, 16, 10, 10]),
        },
        TruncationPhase {
            phase_id: "after_c3",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 120],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc4",
            client_action: "relu_then_shift",
            shift_bits: Some(32),
            shape: &[1, 84],
            pool_kernel: None,
            input_shape: None,
        },
        TruncationPhase {
            phase_id: "after_fc5",
            client_action: "logits_only",
            shift_bits: None,
            shape: &[1, 10],
            pool_kernel: None,
            input_shape: None,
        },
    ],
};
