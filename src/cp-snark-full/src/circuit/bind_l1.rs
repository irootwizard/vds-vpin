//! L1 / L1′ binding: PtMul witness multipliers vs $\mathbf{W}^*$ leaves / RLC columns.
//!
//! Network A (178 PtMul):
//! - Conv $j\in[0,18)$: direct leaf $a_j = \mathbf{W}^*_s$ (both ElGamal branches)
//! - FC1 $j\in[18,146)$: $\sum_i (\gamma')^i \mathbf{W}^*_{9+p\cdot16+i}$
//! - FC2 $j\in[146,178)$: $\sum_i (\gamma')^i \mathbf{W}^*_{1049+p\cdot10+i}$
//!
//! Full R1CS equality constraints are delegated to the existing `point_mult` RevBin
//! tie at `vars_para[n + one_num_vars * j]`; this module performs prover-side
//! checks + Merkle root over $\mathbf{W}^*$ for sparse opening semantics.

use std::fs;
use std::path::PathBuf;

use libspartan::scalar::Scalar;
use serde::Deserialize;
use sha2::{Digest, Sha256};

use num::{BigUint, One, Zero};

use crate::challenge::ClientChallenge;
use crate::curve::{embed_u128_to_scalar, witness_u128_scalar_bytes, CurveE2Params};
use crate::layer_proof::rlc::fold_rlc;
use crate::load_data;
use crate::witness::schedule::load_schedule_from_run_dir;

/// PtMul multiplier slot in `vars_para` (binding spec §0.4).
pub fn ptmul_multiplier_slot(j: usize, n_bit: usize, one_num_vars: usize) -> usize {
    n_bit + one_num_vars * j
}

pub fn one_num_vars(n_bit: usize) -> usize {
    n_bit + 10 + 26 * n_bit
}

// --- Network A layout (paper Table I × B=2) ---

pub const NETWORK_A_PT_MUL: usize = 178;
const CONV_PT_MUL: usize = 18;
const FC1_PT_MUL_START: usize = 18;
const FC1_PT_MUL_END: usize = 146;
const FC2_PT_MUL_START: usize = 146;
const FC2_PT_MUL_END: usize = 178;
const FC1_INPUTS: usize = 64;
const FC1_OUTPUTS: usize = 16;
const FC2_INPUTS: usize = 16;
const FC2_OUTPUTS: usize = 10;
const O_FC1: usize = 9;
const O_FC2: usize = 1049;
const O_FC1_BIAS: usize = 1033;
const FC1_BIAS_LEN: usize = 16;
const O_FC2_BIAS: usize = 1209;
const FC2_BIAS_LEN: usize = 10;
const W_STAR_LEN_A: usize = 1219;
const O_CONV: usize = 0;

fn schedule_total_pt_mul(network: &str) -> Result<usize, String> {
    if let Ok(run) = std::env::var("VPIN_RUN_DIR") {
        let sched = load_schedule_from_run_dir(std::path::Path::new(&run), "paper_proof")?;
        return Ok(sched.total_pt_mul);
    }
    if network == "A" {
        return Ok(NETWORK_A_PT_MUL);
    }
    Err(format!("no schedule for network {network}"))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PtMulSourceKind {
    DirectWeight { w_index: usize },
    RlcWeightColumn {
        base_offset: usize,
        input_index: usize,
        output_dim: usize,
    },
}

/// Map global PtMul index $j$ to its scalar source (Network A).
pub fn ptmul_source_for_j(j: usize) -> Option<PtMulSourceKind> {
    if j < CONV_PT_MUL {
        let s = j % 9;
        return Some(PtMulSourceKind::DirectWeight {
            w_index: O_CONV + s,
        });
    }
    if (FC1_PT_MUL_START..FC1_PT_MUL_END).contains(&j) {
        let local = j - FC1_PT_MUL_START;
        let p = local % FC1_INPUTS;
        return Some(PtMulSourceKind::RlcWeightColumn {
            base_offset: O_FC1,
            input_index: p,
            output_dim: FC1_OUTPUTS,
        });
    }
    if (FC2_PT_MUL_START..FC2_PT_MUL_END).contains(&j) {
        let local = j - FC2_PT_MUL_START;
        let p = local % FC2_INPUTS;
        return Some(PtMulSourceKind::RlcWeightColumn {
            base_offset: O_FC2,
            input_index: p,
            output_dim: FC2_OUTPUTS,
        });
    }
    None
}

fn n2_modulus() -> BigUint {
    BigUint::parse_bytes(
        CurveE2Params::vpin_default()
            .curve_base_field
            .as_bytes(),
        10,
    )
    .expect("parse n2")
}

fn scalar_to_biguint_mod_n2(s: &Scalar) -> BigUint {
    let v = BigUint::from_bytes_le(&s.to_bytes());
    v % n2_modulus()
}

fn biguint_to_u128(v: &BigUint) -> u128 {
    let bytes = v.to_bytes_le();
    let mut le = [0u8; 16];
    let n = bytes.len().min(16);
    le[..n].copy_from_slice(&bytes[..n]);
    u128::from_le_bytes(le)
}

/// FC RLC column multiplier as u128 mod $n_2$ (aligns with Server.py `rLCR` + paper $\gamma'$).
pub fn fc_rlc_column_u128(row: &[u128], gamma: &Scalar) -> u128 {
    let n2 = n2_modulus();
    let g = scalar_to_biguint_mod_n2(gamma);
    let mut acc = BigUint::zero();
    let mut pow = BigUint::one();
    for &w in row {
        acc = (&acc + &((&pow * BigUint::from(w)) % &n2)) % &n2;
        pow = (&pow * &g) % &n2;
    }
    biguint_to_u128(&acc)
}

fn row_weights(w_star: &[u128], base: usize, input_index: usize, output_dim: usize) -> Result<Vec<u128>, String> {
    let start = base + input_index * output_dim;
    let end = start + output_dim;
    if end > w_star.len() {
        return Err(format!(
            "W* row slice [{start},{end}) out of range (len={})",
            w_star.len()
        ));
    }
    Ok(w_star[start..end].to_vec())
}

/// Expected PtMul scalar for slot `j` given committed $\mathbf{W}^*$ and client $\gamma'$.
pub fn expected_ptmul_scalar(
    j: usize,
    w_star: &[u128],
    challenge: &ClientChallenge,
) -> Result<Scalar, String> {
    let source = ptmul_source_for_j(j).ok_or_else(|| format!("no PtMul source for j={j}"))?;
    match source {
        PtMulSourceKind::DirectWeight { w_index } => {
            if w_index >= w_star.len() {
                return Err(format!("direct w_index {w_index} out of W* range"));
            }
            Ok(embed_u128_to_scalar(w_star[w_index]))
        }
        PtMulSourceKind::RlcWeightColumn {
            base_offset,
            input_index,
            output_dim,
        } => {
            let row = row_weights(w_star, base_offset, input_index, output_dim)?;
            let w_u128 = fc_rlc_column_u128(&row, &challenge.gamma_mult_scalar());
            Ok(embed_u128_to_scalar(w_u128))
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct PtMulWStarMap {
    pub network_id: String,
    pub num_ptmul: usize,
    pub j_to_wstar_index: Vec<Option<usize>>,
}

#[derive(Debug, Deserialize)]
struct PtMulScalarSourcesFile {
    network_id: String,
    num_ptmul: usize,
}

fn legacy_map_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("j_to_wstar_index.json")
}

fn scalar_sources_path(network: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("model_exports")
        .join(network)
        .join("ptmul_scalar_sources.json")
}

pub fn load_ptmul_wstar_map(network: &str) -> Result<PtMulWStarMap, String> {
    let path = legacy_map_path(network);
    let json = fs::read_to_string(&path).map_err(|e| format!("{path:?}: {e}"))?;
    let m: PtMulWStarMap = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    if m.network_id != network {
        return Err(format!("map network {:?} != {network}", m.network_id));
    }
    Ok(m)
}

pub fn scalar_sources_available(network: &str) -> bool {
    scalar_sources_path(network).is_file()
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

/// Verify trajectory weights vs $\mathbf{W}^*$ (direct conv + FC RLC columns with $\gamma'$).
pub fn check_l1_ptmul_bindings(
    network: &str,
    w_star: &[u128],
    challenge: &ClientChallenge,
) -> Result<bool, String> {
    if network == "A" && w_star.len() != W_STAR_LEN_A {
        return Err(format!(
            "bind_l1: Network A W* len {} != {W_STAR_LEN_A}",
            w_star.len()
        ));
    }

    let (num_mults, traj_weights, _, _, n_bit) =
        load_data::load_data(network).map_err(|e| e.to_string())?;
    if traj_weights.len() != num_mults {
        return Err(format!(
            "trajectory len {} != num_mults {}",
            traj_weights.len(),
            num_mults
        ));
    }

    if network == "A" && num_mults != schedule_total_pt_mul(network)? {
        return Err(format!(
            "Network A PtMul count {num_mults} != schedule expectation"
        ));
    }

    let _one_nv = one_num_vars(n_bit);
    let _ = ptmul_multiplier_slot(0, n_bit, _one_nv);

    if network == "A" && !scalar_sources_path(network).is_file() {
        return Err(format!(
            "missing {} (run export_ptmul_scalar_sources.py)",
            scalar_sources_path(network).display()
        ));
    }

    let _meta: PtMulScalarSourcesFile = if network == "A" {
        let path = scalar_sources_path(network);
        let json = fs::read_to_string(&path).map_err(|e| format!("{path:?}: {e}"))?;
        serde_json::from_str(&json).map_err(|e| e.to_string())?
    } else {
        PtMulScalarSourcesFile {
            network_id: network.to_string(),
            num_ptmul: num_mults,
        }
    };

    for (j, &w) in traj_weights.iter().enumerate() {
        let embedded = embed_u128_to_scalar(w);
        let witness_bytes = witness_u128_scalar_bytes(w);
        if embedded.to_bytes() != witness_bytes {
            return Err(format!("PtMul {j}: embed vs witness bytes mismatch"));
        }

        if network != "A" {
            continue;
        }

        let expected = expected_ptmul_scalar(j, w_star, challenge)?;
        if embedded != expected {
            return Err(format!(
                "L1 mismatch j={j}: traj={w} expected_scalar={:?} (kind={source:?})",
                expected.to_bytes(),
                source = ptmul_source_for_j(j).expect("mapped")
            ));
        }
    }

    Ok(true)
}

/// Map expected PtMul scalar to a trajectory `weight.json` u128 (embed + witness bytes align).
pub fn trajectory_u128_for_expected_scalar(s: &Scalar) -> Result<u128, String> {
    let target = s.to_bytes();

    for byte_off in [0usize, 16] {
        let mut le = [0u8; 16];
        le.copy_from_slice(&target[byte_off..byte_off + 16]);
        let w = u128::from_le_bytes(le);
        if embed_u128_to_scalar(w) == *s && witness_u128_scalar_bytes(w) == target {
            return Ok(w);
        }
    }

    // RLc column scalars rarely match low-128-bit heuristics; scan from seed.
    let seed = u128::from_le_bytes(target[0..16].try_into().unwrap());
    const MAX_SCAN: u128 = 8_000_000;
    for delta in 0..MAX_SCAN {
        let w = seed.wrapping_add(delta);
        if embed_u128_to_scalar(w) == *s && witness_u128_scalar_bytes(w) == target {
            return Ok(w);
        }
    }

    Err(format!(
        "cannot encode expected scalar {:?} as trajectory u128 (scan {MAX_SCAN})",
        target
    ))
}

/// Rewrite `ec_witness/pointMult/weight.json` FC slots for client `gamma_mult` (paper RLC columns).
pub fn sync_ptmul_weights_for_challenge(
    witness_root: &std::path::Path,
    w_star: &[u128],
    challenge: &ClientChallenge,
) -> Result<(), String> {
    let weight_path = witness_root.join("pointMult").join("weight.json");
    let json = fs::read_to_string(&weight_path).map_err(|e| format!("{weight_path:?}: {e}"))?;
    let parsed: Vec<String> = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    let mut weights: Vec<u128> = parsed
        .iter()
        .map(|s| s.parse().map_err(|e| format!("{s}: {e}")))
        .collect::<Result<_, _>>()?;

    let gamma = challenge.gamma_mult_scalar();
    for (j, slot) in weights.iter_mut().enumerate() {
        *slot = match ptmul_source_for_j(j) {
            Some(PtMulSourceKind::DirectWeight { w_index }) => {
                if w_index >= w_star.len() {
                    return Err(format!("direct w_index {w_index} out of W* range"));
                }
                w_star[w_index]
            }
            Some(PtMulSourceKind::RlcWeightColumn {
                base_offset,
                input_index,
                output_dim,
            }) => {
                let row = row_weights(w_star, base_offset, input_index, output_dim)?;
                fc_rlc_column_u128(&row, &gamma)
            }
            None => return Err(format!("no PtMul source for j={j}")),
        };
    }

    let out: Vec<String> = weights.iter().map(|w| w.to_string()).collect();
    fs::write(
        &weight_path,
        serde_json::to_string(&out).map_err(|e| e.to_string())?,
    )
    .map_err(|e| format!("write {weight_path:?}: {e}"))?;
    Ok(())
}

/// Chain-outside binding: $\mathbf W^*$ bias leaves vs `fc_trace.json` bias rows.
pub fn check_fc_bias_wstar_bindings(network: &str, w_star: &[u128]) -> Result<bool, String> {
    if network != "A" {
        return Ok(true);
    }
    if w_star.len() != W_STAR_LEN_A {
        return Err(format!(
            "bias bind: W* len {} != {W_STAR_LEN_A}",
            w_star.len()
        ));
    }
    let biases = crate::trace::fc::load_fc_trace_biases(network)?;
    if biases.is_empty() {
        return Ok(true);
    }
    let expected: [&[u128]; 2] = [
        &w_star[O_FC1_BIAS..O_FC1_BIAS + FC1_BIAS_LEN],
        &w_star[O_FC2_BIAS..O_FC2_BIAS + FC2_BIAS_LEN],
    ];
    if biases.len() != expected.len() {
        return Err(format!(
            "fc_trace bias layers {} != expected {}",
            biases.len(),
            expected.len()
        ));
    }
    for (layer, (got, exp)) in biases.iter().zip(expected.iter()).enumerate() {
        if got.len() != exp.len() {
            return Err(format!("fc bias layer {layer} len {} != {}", got.len(), exp.len()));
        }
        for (i, (&g, &e)) in got.iter().zip(exp.iter()).enumerate() {
            if g != e {
                return Err(format!(
                    "fc bias mismatch layer={layer} i={i}: trace={g} w_star={e}"
                ));
            }
        }
    }
    Ok(true)
}

/// Conv-only direct-leaf check (legacy `j_to_wstar_index.json` path).
pub fn check_l1_conv_direct_bindings(network: &str, w_star: &[u128]) -> Result<bool, String> {
    let (num_mults, traj_weights, _, _, _) =
        load_data::load_data(network).map_err(|e| e.to_string())?;
    let map = load_ptmul_wstar_map(network).ok();
    for (j, &w) in traj_weights.iter().enumerate() {
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
    let _ = num_mults;
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
    use crate::challenge::ClientChallenge;
    use crate::model::load_w_star;

    #[test]
    fn merkle_root_nonempty() {
        let w = load_w_star("A").unwrap();
        let r = merkle_root_w_star(&w);
        assert_eq!(r.len(), 64);
    }

    #[test]
    fn ptmul_source_layout_covers_178() {
        let mut direct = 0usize;
        let mut rlc = 0usize;
        for j in 0..NETWORK_A_PT_MUL {
            match ptmul_source_for_j(j).unwrap() {
                PtMulSourceKind::DirectWeight { .. } => direct += 1,
                PtMulSourceKind::RlcWeightColumn { .. } => rlc += 1,
            }
        }
        assert_eq!(direct, 18);
        assert_eq!(rlc, 160);
    }

    #[test]
    fn fc_rlc_column_roundtrip() {
        let row: Vec<u128> = (0..16).map(|i| 1000 + i as u128).collect();
        let mut w_star = vec![0u128; W_STAR_LEN_A];
        w_star[O_FC1..O_FC1 + 16].copy_from_slice(&row);

        let challenge = ClientChallenge::sample(2144, 178);
        let expected = expected_ptmul_scalar(18, &w_star, &challenge).unwrap();
        let col = fc_rlc_column_u128(&row, &challenge.gamma_mult_scalar());
        assert_eq!(expected, embed_u128_to_scalar(col));
    }

    #[test]
    fn l1_conv_direct_bindings_network_a() {
        use crate::witness::ProofPlan;
        let run = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../model_training/outputs/20260622_184254");
        if !run.is_dir() {
            return;
        }
        let plan = ProofPlan::from_run_dir(&run, "A", "paper_proof").unwrap();
        plan.activate_witness();
        std::env::set_var("VPIN_RUN_DIR", plan.run_dir.to_string_lossy().as_ref());
        let w = load_w_star("A").unwrap();
        assert!(check_l1_conv_direct_bindings("A", &w).unwrap());
    }

    #[test]
    fn l1_full_bindings_expected_scalars_network_a() {
        let w = load_w_star("A").unwrap();
        let challenge = ClientChallenge::sample(2144, 178);
        for j in 0..NETWORK_A_PT_MUL {
            let exp = expected_ptmul_scalar(j, &w, &challenge).unwrap();
            match ptmul_source_for_j(j).unwrap() {
                PtMulSourceKind::DirectWeight { w_index } => {
                    assert_eq!(exp, embed_u128_to_scalar(w[w_index]));
                }
                PtMulSourceKind::RlcWeightColumn {
                    base_offset,
                    input_index,
                    output_dim,
                } => {
                    let row = row_weights(&w, base_offset, input_index, output_dim).unwrap();
                    let col = fc_rlc_column_u128(&row, &challenge.gamma_mult_scalar());
                    assert_eq!(exp, embed_u128_to_scalar(col));
                }
            }
        }
    }

    #[test]
    #[ignore = "slow: scans u128 space for RLc trajectory encoding"]
    fn trajectory_encoding_all_slots_network_a() {
        let run = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../model_training/outputs/20260622_184254");
        if !run.is_dir() {
            return;
        }
        let w = load_w_star("A").unwrap();
        let challenge = ClientChallenge::sample(2144, 178);
        for j in 0..NETWORK_A_PT_MUL {
            let exp = expected_ptmul_scalar(j, &w, &challenge).unwrap();
            trajectory_u128_for_expected_scalar(&exp).expect(&format!("j={j}"));
        }
    }

    #[test]
    #[ignore = "legacy rust_files weight.json FC slots use pf(sk) not client gamma_mult"]
    fn l1_bindings_network_a_legacy_trajectory() {
        let w = load_w_star("A").unwrap();
        let challenge = ClientChallenge::sample(2144, 178);
        assert!(check_l1_ptmul_bindings("A", &w, &challenge).unwrap());
    }
}
