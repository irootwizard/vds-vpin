//! EC gadget schedules implied by the paper (PtAdd / PtMul), pre-R1CS wiring.
//!
//! These mirror what `cnn_networks/Server.py` appends to `point_one_Add`,
//! `point_two_Add`, `points_mult`, and `weights_array` during homomorphic inference.

/// One scalar-multiply gadget witness slot (homomorphic base × scalar weight).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PtMulSlot {
    pub base_scalar: u128,
    pub weight_scalar: u128,
}

/// One point-addition gadget witness slot.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PtAddSlot {
    pub augend: u128,
    pub addend: u128,
}

/// Gadget batch for one layer proof instance (paper §IV–V).
#[derive(Clone, Debug, Default)]
pub struct LayerGadgetSchedule {
    pub pt_muls: Vec<PtMulSlot>,
    pub pt_adds: Vec<PtAddSlot>,
}

impl LayerGadgetSchedule {
    pub fn num_pt_muls(&self) -> usize {
        self.pt_muls.len()
    }

    pub fn num_pt_adds(&self) -> usize {
        self.pt_adds.len()
    }
}
