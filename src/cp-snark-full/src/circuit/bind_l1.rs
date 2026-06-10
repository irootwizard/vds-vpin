//! L1 / L1′ binding: PtMul witness multipliers vs $\mathbf{W}^*$ leaves.
//!
//! Full R1CS equality constraints are delegated to the existing `point_mult` RevBin
//! tie at `vars_para[n + one_num_vars * j]`; this module performs prover-side
//! checks + Merkle root over $\mathbf{W}^*$ for sparse opening semantics.

use std::fs;
use std::path::PathBuf;

use libspartan::scalar::Scalar;
use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::curve::{embed_u128_to_scalar, witness_u128_scalar_bytes};
use crate::load_data;

/// PtMul multiplier slot in `vars_para` (binding spec §0.4).
pub fn ptmul_multiplier_slot(j: usize, n_bit: usize, one_num_vars: usize) -> usize {
    n_bit + one_num_vars * j
}

pub fn one_num_vars(n_bit: usize) -> usize {
    n_bit + 10 + 26 * n_bit
}

#[derive(Debug, Deserialize)]
pub struct PtMulWStarMap {
    pub network_id: String,
    pub num_ptmul: usize,
    pub j_to_wstar_index: Vec<Option<usize>>,
}

fn map_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("j_to_wstar_index.json")
}

pub fn load_ptmul_wstar_map(network: &str) -> Result<PtMulWStarMap, String> {
    let path = map_path(network);
    let json = fs::read_to_string(&path).map_err(|e| format!("{path:?}: {e}"))?;
    let m: PtMulWStarMap = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    if m.network_id != network {
        return Err(format!("map network {:?} != {network}", m.network_id));
    }
    Ok(m)
}

/// SHA256 Merkle root over $\mathbf{W}^*$ leaves (scalar bytes LE).
pub fn merkle_root_w_star(w_star: &[u128]) -> String {
    if w_star.is_empty() {
        return hex::encode(Sha256::digest([]));
    }
    let mut level: Vec<[u8; 32]> = w_star
        .iter()
        .map(|w| {
            let s = embed_u128_to_scalar(*w);
            let mut h = Sha256::new();
            h.update(s.to_bytes());
            let d = h.finalize();
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&d);
            arr
        })
        .collect();
    while level.len() > 1 {
        let mut next = Vec::new();
        for chunk in level.chunks(2) {
            let mut h = Sha256::new();
            h.update(chunk[0]);
            if chunk.len() == 2 {
                h.update(chunk[1]);
            } else {
                h.update(chunk[0]);
            }
            let d = h.finalize();
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&d);
            next.push(arr);
        }
        level = next;
    }
    hex::encode(level[0])
}

/// Verify trajectory weights match witness encoding and direct $\mathbf{W}^*$ leaves.
pub fn check_l1_ptmul_bindings(network: &str, w_star: &[u128]) -> Result<bool, String> {
    let (num_mults, traj_weights, _, _, n_bit) = load_data::load_data(network);
    if traj_weights.len() != num_mults {
        return Err(format!(
            "trajectory len {} != num_mults {}",
            traj_weights.len(),
            num_mults
        ));
    }

    let one_nv = one_num_vars(n_bit);
    let _ = ptmul_multiplier_slot(0, n_bit, one_nv);

    let map = load_ptmul_wstar_map(network).ok();

    for (j, &w) in traj_weights.iter().enumerate() {
        let embedded = embed_u128_to_scalar(w);
        let witness_bytes = witness_u128_scalar_bytes(w);
        if embedded.to_bytes() != witness_bytes {
            return Err(format!("PtMul {j}: embed vs witness bytes mismatch"));
        }

        if let Some(ref m) = map {
            if j >= m.j_to_wstar_index.len() {
                return Err(format!("map shorter than trajectory at j={j}"));
            }
            if let Some(i) = m.j_to_wstar_index[j] {
                if i >= w_star.len() {
                    return Err(format!("map j={j} -> i={i} out of W* range"));
                }
                if w_star[i] != w {
                    return Err(format!(
                        "L1 leaf mismatch j={j} i={i}: w_star={} traj={w}",
                        w_star[i]
                    ));
                }
            }
        }
    }

    Ok(true)
}

/// Compare opened trajectory scalar with R1CS witness slot bytes (post-prove audit).
pub fn witness_slot_matches_trajectory(
    vars_para_bytes: &[u8],
    j: usize,
    n_bit: usize,
    one_num_vars: usize,
    expected: &Scalar,
) -> bool {
    let slot = ptmul_multiplier_slot(j, n_bit, one_num_vars);
    let start = slot * 32;
    let end = start + 32;
    if end > vars_para_bytes.len() {
        return false;
    }
    vars_para_bytes[start..end] == expected.to_bytes()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::load_w_star;

    #[test]
    fn merkle_root_nonempty() {
        let w = load_w_star("A").unwrap();
        let r = merkle_root_w_star(&w);
        assert_eq!(r.len(), 64);
    }

    #[test]
    fn l1_bindings_network_a() {
        let w = load_w_star("A").unwrap();
        assert!(check_l1_ptmul_bindings("A", &w).unwrap());
    }
}
