//! Point addition gadget — counts from rust_files witness.

use crate::trace::{load_data_add, witness_available};

/// Returns `(num_point_adds, num_constraints)` for the requested network.
pub fn point_add_counts(network: &str) -> (usize, usize) {
    if !witness_available(network) {
        return (0, 0);
    }
    let (num_adds, _, _, _, _, _) = load_data_add(network);
    (num_adds, 0)
}

/// Placeholder type for future in-crate R1CS edits.
pub struct PointAddGadgetStub;
