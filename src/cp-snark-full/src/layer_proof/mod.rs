//! Per-layer computational proofs (vPIN paper §IV–V), **without** model-parameter commitment.
//!
//! **Human-readable package guide:** see [`README.md`](README.md) in this directory
//! (parameters per layer, verify vs proof generation, module map).
//!
//! | Layer | Equations | Gadgets |
//! |-------|-----------|---------|
//! | Convolution | (5)/(6) per cell, (9) RLC with **γ** | PtMul, PtAdd |
//! | Avg pool | (7) window sum | PtAdd (+ public scale off-circuit) |
//! | FC | (8) per output, (10) RLC with **γ′** | PtMul, PtAdd |
//! | Activation (TReLU) | — | **Client only** (no server SNARK) |
//!
//! Scalar checks live in `verify` (not SNARK); π generation lives in `circuit_prove` / `protocol`.

pub mod common;
pub mod conv;
pub mod fc;
pub mod gadget;
pub mod pool;
pub mod rlc;
pub mod stack;
pub mod verify;

pub use common::{fold_rlc, LayerProofStage, ProofCoverage};
pub use conv::ConvLayerProofSpec;
pub use fc::FcLayerProofSpec;
pub use gadget::{LayerGadgetSchedule, PtAddSlot, PtMulSlot};
pub use pool::PoolLayerProofSpec;
pub use stack::ServerLinearProofStack;
pub use verify::LayerProofError;
