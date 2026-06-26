//! Point multiplication gadget — counts from rust_files witness.

use crate::trace::{load_data, witness_available};

/// Returns `(num_point_mults, num_constraints)` for the requested network.
pub fn point_mult_counts(network: &str) -> (usize, usize) {
    if !witness_available(network) {
        return (0, 0);
    }
    let (num_mults, _, _, _, _) = load_data(network);
    (num_mults, 0)
}

/// Placeholder type for future in-crate R1CS edits.
pub struct PointMultGadgetStub;
