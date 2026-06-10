//! Placeholder until Z.2 lands. Returns a minimal Instance so `rebuild_instance`
//! never panics; full implementation in [`pool_sum::build_pool_toy_instance`].

use libspartan::scalar::Scalar;
use libspartan::Instance;

pub fn build_pool_toy_instance() -> Instance {
    let one = Scalar::one().to_bytes();
    let a = vec![(0usize, 0usize, one)];
    let b = vec![(0usize, 1usize, one)];
    let c = vec![(0usize, 1usize, one)];
    Instance::new(1, 2, 1, &a, &b, &c).expect("pool_toy stub instance")
}
