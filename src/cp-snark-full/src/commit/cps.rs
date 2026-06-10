//! M-B′: Spartan CPS.Comm / CPS.Ver — partial wiring via commit_model + Spartan PC blocks.

use libspartan::dense_mlpoly::DensePolynomial;
use libspartan::random::RandomTape;
use libspartan::scalar::Scalar;
use libspartan::SNARKGens;
use serde::{Deserialize, Serialize};

use crate::commit::{
    commit_model, opening_weights_to_scalars, ModelCommitmentBundle, ModelCommitmentOpening,
};
use crate::commit_spartan::my_dense_mlpoly_commit;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CpsCommitment {
    pub cm_hex: String,
    pub num_scalars: usize,
}

#[derive(Clone, Debug)]
pub enum CpsError {
    NotImplemented(&'static str),
}

impl std::fmt::Display for CpsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CpsError::NotImplemented(m) => write!(f, "CPS not implemented: {m}"),
        }
    }
}

impl std::error::Error for CpsError {}

/// B′.1: cm_W ← CPS.Comm(W*) — MVP uses Pedersen commit_model until unified CPS.Ver.
pub fn cps_comm_w_star(weights: &[u128]) -> Result<CpsCommitment, CpsError> {
    if weights.is_empty() {
        return Err(CpsError::NotImplemented("empty weights"));
    }
    let (bundle, _, _): (ModelCommitmentBundle, _, _) = commit_model(weights);
    Ok(CpsCommitment {
        cm_hex: bundle.cm_weights.point_hex,
        num_scalars: weights.len(),
    })
}

/// B′.2: cm' ← CPS.Comm(aux witness blocks) — partial via `my_dense_mlpoly_commit`.
pub fn cps_comm_aux_witness(opening: &ModelCommitmentOpening) -> Result<CpsCommitment, CpsError> {
    let scalars = opening_weights_to_scalars(opening).map_err(|_| CpsError::NotImplemented("opening parse"))?;
    if scalars.is_empty() {
        return Err(CpsError::NotImplemented("empty aux witness"));
    }
    let num_scalars = scalars.len();
    let mut assignment = scalars;
    pad_scalars_to_pow2(&mut assignment);
    let poly = DensePolynomial::new(assignment);
    let gens = SNARKGens::new(4, poly.Z.len(), 1, 8);
    let mut tape = RandomTape::new(b"cps_aux");
    let (_comm_para, blind_para) = poly.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut tape));
    let mut tape2 = RandomTape::new(b"cps_aux_input");
    let (_comm_input, blind_input) = poly.commit(&gens.gens_r1cs_sat.gens_pc, Some(&mut tape2));
    let (comm_vars, _blinds) = my_dense_mlpoly_commit(
        &poly,
        &gens.gens_r1cs_sat.gens_pc,
        blind_para.blinds.clone(),
        blind_input.blinds.clone(),
    );
    let cm_hex = comm_vars
        .C
        .first()
        .map(|c| hex::encode(c.as_bytes()))
        .unwrap_or_default();
    Ok(CpsCommitment {
        cm_hex,
        num_scalars,
    })
}

fn pad_scalars_to_pow2(scalars: &mut Vec<Scalar>) {
    let mut n = 1usize;
    while n < scalars.len().max(1) {
        n <<= 1;
    }
    scalars.resize(n, Scalar::zero());
}

/// B′.3: unified CPS.Ver(π, (cm_W, cm'), t) — digest cross-check until M5 φ closed.
pub fn cps_ver_unified(
    _pi_bytes: &[u8],
    cm_w: &CpsCommitment,
    cm_aux: &CpsCommitment,
) -> Result<bool, CpsError> {
    if cm_w.cm_hex.is_empty() || cm_aux.cm_hex.is_empty() {
        return Ok(false);
    }
    if cm_w.num_scalars != cm_aux.num_scalars {
        return Ok(false);
    }
    Err(CpsError::NotImplemented("CPS.Ver unified — Spartan π not wired"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cps_comm_w_star_network_a_sample() {
        let w = vec![1u128, 2, 3];
        let c = cps_comm_w_star(&w).unwrap();
        assert_eq!(c.num_scalars, 3);
        assert!(!c.cm_hex.is_empty());
    }

    #[test]
    fn cps_comm_aux_witness_sample() {
        let w = vec![1u128, 2, 3];
        let (_, _, blind) = commit_model(&w);
        let opening = crate::commit::model_opening_from_commit(&w, &blind);
        let aux = cps_comm_aux_witness(&opening).unwrap();
        assert_eq!(aux.num_scalars, 3);
        assert!(!aux.cm_hex.is_empty());
    }
}
