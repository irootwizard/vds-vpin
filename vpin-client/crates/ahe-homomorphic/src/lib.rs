mod network_a;
mod network_a_ec;
mod network_lenet;
mod network_resnet;
mod plain_forward;

pub use network_a::{
    avg_pool_ciphertext, conv2_ciphertext, fc1_layer, fc2_layer, flatten_ciphertext,
    get_op_counters, reset_op_counters,
};
pub use network_lenet::{
    lenet_cifar_c3, lenet_cifar_conv1, lenet_cifar_conv2, lenet_cifar_fc4, lenet_cifar_fc5,
    lenet_flatten, lenet_mnist_c3, lenet_mnist_conv1, lenet_mnist_conv2, lenet_mnist_fc4,
    lenet_mnist_fc5,
};
pub use network_a_ec::{
    avg_pool_ciphertext_ec, conv2_ciphertext_ec, fc1_layer_ec, fc2_layer_ec,
    flatten_ciphertext_ec, get_ec_op_counters, reset_ec_op_counters,
};
pub use plain_forward::{
    conv2d_int32, numpy_homomorphic_plain, pool_sum_fixed, PlainForwardLayers, TruncationPlan,
};
pub use network_resnet::{
    encrypt_bias_f32 as encrypt_resnet_bias_f32, resnet_add_ds_shortcut, resnet_add_identity_shortcut,
    resnet_avgpool_fc, resnet_conv_ciphertext,
};
