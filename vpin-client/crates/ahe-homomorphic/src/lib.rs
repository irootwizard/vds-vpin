mod network_a;
mod network_a_ec;
mod plain_forward;

pub use network_a::{
    avg_pool_ciphertext, conv2_ciphertext, fc1_layer, fc2_layer, flatten_ciphertext,
    get_op_counters, reset_op_counters,
};
pub use network_a_ec::{
    avg_pool_ciphertext_ec, conv2_ciphertext_ec, fc1_layer_ec, fc2_layer_ec,
    flatten_ciphertext_ec, get_ec_op_counters, reset_ec_op_counters,
};
pub use plain_forward::{
    conv2d_int32, numpy_homomorphic_plain, pool_sum_fixed, PlainForwardLayers, TruncationPlan,
};
