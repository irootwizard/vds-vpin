//! EC gadget skeleton — full R1CS migration in A1-1 (vPIN_proof_generation reference).

mod point_add;
mod point_mult;

pub use point_add::{point_add_counts, PointAddGadgetStub};
pub use point_mult::{point_mult_counts, PointMultGadgetStub};
