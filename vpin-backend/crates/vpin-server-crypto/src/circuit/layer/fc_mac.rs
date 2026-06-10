//! Placeholder until Z.3 lands. Returns a minimal Instance so `rebuild_instance`
//! never panics; full implementation in [`fc_mac::build_fc_toy_instance`].

use libspartan::scalar::Scalar;
use libspartan::Instance;

pub fn build_fc_toy_instance() -> Instance {
    let one = Scalar::one().to_bytes();
    let a = vec![(0usize, 0usize, one)];
    let b = vec![(0usize, 1usize, one)];
    let c = vec![(0usize, 1usize, one)];
    Instance::new(1, 2, 1, &a, &b, &c).expect("fc_toy stub instance")
}
