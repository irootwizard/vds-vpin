//! E2 curve arithmetic via primeorder.

use crate::curve::E2;
use crate::{FieldElement, Scalar};
use elliptic_curve::{CurveArithmetic, PrimeCurveArithmetic, hazmat::FieldArithmetic};
use primefield::PrimeFieldExt;
use primeorder::{
    mul_backend::PrecomputedTables, BasepointTable, PrimeCurveParams, PrimeCurveWithBasepointTable,
    point_arithmetic,
};

pub type AffinePoint = primeorder::AffinePoint<E2>;
pub type ProjectivePoint = primeorder::ProjectivePoint<E2>;

/// `1 + Scalar::NUM_BITS / 8` for 256-bit scalars.
pub const BASEPOINT_WINDOW: usize = 33;

pub(crate) static E2_BASEPOINT_TABLE: BasepointTable<ProjectivePoint, BASEPOINT_WINDOW> =
    BasepointTable::new();

impl CurveArithmetic for E2 {
    type AffinePoint = AffinePoint;
    type ProjectivePoint = ProjectivePoint;
    type Scalar = Scalar;
}

impl FieldArithmetic for E2 {
    type FieldElement = FieldElement;
}

impl PrimeCurveArithmetic for E2 {
    type CurveGroup = ProjectivePoint;
}

impl PrimeCurveWithBasepointTable<BASEPOINT_WINDOW> for E2 {
    const BASEPOINT_TABLE: &'static BasepointTable<ProjectivePoint, BASEPOINT_WINDOW> =
        &E2_BASEPOINT_TABLE;
}

impl PrimeCurveParams for E2 {
    type PointArithmetic = point_arithmetic::EquationAIsGeneric;
    type Backend = PrecomputedTables<BASEPOINT_WINDOW>;

    const EQUATION_A: FieldElement =
        FieldElement::from_hex_vartime(crate::params::COEFF_A_HEX);
    const EQUATION_B: FieldElement = FieldElement::from_hex_vartime(crate::params::COEFF_B_HEX);
    const GENERATOR: (FieldElement, FieldElement) = (
        FieldElement::from_hex_vartime(crate::params::GENERATOR_X_HEX),
        FieldElement::from_hex_vartime(crate::params::GENERATOR_Y_HEX),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use elliptic_curve::group::Group;

    #[test]
    fn generator_non_identity() {
        assert!(!bool::from(ProjectivePoint::GENERATOR.is_identity()));
    }
}
