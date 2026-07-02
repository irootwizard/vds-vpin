//! EC-backend tensor codec (encrypt / decrypt grids) — wire-compatible with ark stack.

mod bridge;
pub use bridge::{
    ark_grid2_to_ec, ark_tensor4_to_ec, ark_to_ec, ec_grid2_to_ark, ec_tensor4_to_ark, ec_to_ark,
};
pub use ahe_codec::{
    apply_client_action, fixed_point_to_real, real_to_fixed_point, ClientAction,
    FIXED_POINT_BITS, PARALLEL_THRESHOLD,
};
pub use ahe_crypto_e2_ec::{BsgsError, BsgsTable, EcE2Point, EcKeyMaterial};

use ahe_crypto_e2_ec::{encrypt_scalar_with_r, EcCiphertext};
use num_bigint::BigUint;
use num_traits::One;
use rand::Rng;
use rayon::prelude::*;

pub fn encrypt_scalar<R: Rng>(
    plaintext: i64,
    generator: &EcE2Point,
    public_key: &EcE2Point,
    curve_order: &BigUint,
    rng: &mut R,
) -> EcCiphertext {
    let max = curve_order - BigUint::one();
    let r = loop {
        let bytes: [u8; 32] = rng.gen();
        let candidate = BigUint::from_bytes_be(&bytes);
        if candidate > BigUint::one() && candidate < max {
            break candidate;
        }
    };
    encrypt_scalar_with_r(plaintext, generator, public_key, &r, curve_order)
}

pub fn decrypt_tensor(
    keys: &EcKeyMaterial,
    c1_cells: &[EcE2Point],
    c2_cells: &[EcE2Point],
    table: &BsgsTable,
) -> Result<Vec<i64>, BsgsError> {
    assert_eq!(c1_cells.len(), c2_cells.len());
    let n = c1_cells.len();
    let mut out = Vec::with_capacity(n);
    let mut first_err: Option<String> = None;
    let mut ok_count = 0u64;
    let mut err_count = 0u64;
    for (i, (a, b)) in c1_cells.iter().zip(c2_cells.iter()).enumerate() {
        match keys.decrypt_pair(a, b, table) {
            Ok(v) => {
                if i < 5 || i % 10000 == 0 {
                    eprintln!("[decrypt_tensor] i={i}/{n} v={v}");
                }
                out.push(v);
                ok_count += 1;
            }
            Err(e) => {
                err_count += 1;
                if first_err.is_none() {
                    first_err = Some(format!("i={i}/{n}: {e}"));
                    let msg = first_err.as_ref().unwrap();
                    eprintln!("[decrypt_tensor] FIRST ERROR at {msg}");
                }
                // push 0 as placeholder so we don't lose alignment
                out.push(0);
            }
        }
    }
    eprintln!("[decrypt_tensor] done: ok={ok_count} err={err_count} total={n}");
    if let Some(msg) = first_err {
        Err(BsgsError::Invalid(msg))
    } else {
        Ok(out)
    }
}

pub fn encrypt_tensor<R: Rng>(
    plaintexts: &[i32],
    keys: &EcKeyMaterial,
    rng: &mut R,
) -> (Vec<EcE2Point>, Vec<EcE2Point>) {
    let n = plaintexts.len();
    let order = keys.curve_order.clone();
    let g = keys.generator.clone();
    let pk = keys.public_key.clone();
    if n >= PARALLEL_THRESHOLD {
        let cts: Vec<EcCiphertext> = plaintexts
            .par_iter()
            .map(|&m| {
                let mut local = rand::thread_rng();
                encrypt_scalar(m as i64, &g, &pk, &order, &mut local)
            })
            .collect();
        (
            cts.iter().map(|c| c.c1.clone()).collect(),
            cts.iter().map(|c| c.c2.clone()).collect(),
        )
    } else {
        let mut c1 = Vec::with_capacity(n);
        let mut c2 = Vec::with_capacity(n);
        for &m in plaintexts {
            let ct = encrypt_scalar(m as i64, &g, &pk, &order, rng);
            c1.push(ct.c1);
            c2.push(ct.c2);
        }
        (c1, c2)
    }
}

pub type SharedBsgsTable = std::sync::Arc<BsgsTable>;

pub fn load_bsgs(path: &std::path::Path) -> Result<SharedBsgsTable, BsgsError> {
    BsgsTable::load(path).map(std::sync::Arc::new)
}
