use std::path::PathBuf;

use ahe_codec::{decrypt_pair, encrypt_scalar_with_r, BsgsTable};
use ahe_crypto_e2::{be32_to_coord, CurveE2, E2Point, KeyMaterial};
use num_bigint::BigUint;
use serde_json::Value;

fn fixture_paths() -> (PathBuf, PathBuf) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures");
    (root.join("e2_vectors.json"), root.join("table.bin"))
}

fn parse_biguint(v: &Value, key: &str) -> BigUint {
    let s = v[key].as_str().expect("string field");
    BigUint::parse_bytes(s.as_bytes(), 10).expect("parse biguint")
}

fn parse_private_scalar(raw: &str) -> BigUint {
    let key = "\"private_scalar\":";
    let tail = raw.split(key).nth(1).expect("private scalar key");
    let digits = tail
        .split(',')
        .next()
        .expect("private scalar value")
        .trim();
    BigUint::parse_bytes(digits.as_bytes(), 10).expect("parse private scalar")
}

#[test]
fn e2_curve_and_codec_match_python_vectors() {
    let (vector_path, table_path) = fixture_paths();
    let raw = std::fs::read_to_string(&vector_path).expect("read e2_vectors");
    let v: Value = serde_json::from_str(&raw).expect("parse e2_vectors");

    let g_aff = CurveE2::generator();
    let gx = CurveE2::coord_x_be(&g_aff).expect("gx");
    let gy = CurveE2::coord_y_be(&g_aff).expect("gy");
    assert_eq!(
        be32_to_coord(&gx),
        parse_biguint(&v, "generator_x"),
        "generator x mismatch"
    );
    assert_eq!(
        be32_to_coord(&gy),
        parse_biguint(&v, "generator_y"),
        "generator y mismatch"
    );

    let sk = parse_private_scalar(&raw);
    let keys = KeyMaterial::key_gen_deterministic(sk);
    let (pkx, pky) = match keys.public_key {
        E2Point::Affine { x, y } => (be32_to_coord(&x), be32_to_coord(&y)),
        E2Point::Identity => panic!("public key is identity"),
    };
    assert_eq!(pkx, parse_biguint(&v, "public_key_x"), "public key x mismatch");
    assert_eq!(pky, parse_biguint(&v, "public_key_y"), "public key y mismatch");

    let et = &v["encrypt_test"];
    let plaintext = et["plaintext"].as_i64().expect("plaintext");
    let r = BigUint::from(et["r"].as_u64().expect("nonce r"));
    let ct = encrypt_scalar_with_r(
        plaintext,
        &keys.generator,
        &keys.public_key,
        &r,
        &keys.curve_order,
    );
    let (c1x, c1y) = match ct.c1 {
        E2Point::Affine { x, y } => (be32_to_coord(&x), be32_to_coord(&y)),
        E2Point::Identity => panic!("c1 identity"),
    };
    let (c2x, c2y) = match ct.c2 {
        E2Point::Affine { x, y } => (be32_to_coord(&x), be32_to_coord(&y)),
        E2Point::Identity => panic!("c2 identity"),
    };
    assert_eq!(c1x, parse_biguint(et, "c1_x"), "c1 x mismatch");
    assert_eq!(c1y, parse_biguint(et, "c1_y"), "c1 y mismatch");
    assert_eq!(c2x, parse_biguint(et, "c2_x"), "c2 x mismatch");
    assert_eq!(c2y, parse_biguint(et, "c2_y"), "c2 y mismatch");

    if table_path.is_file() {
        let table = BsgsTable::load(&table_path).expect("load table.bin");
        let dec = decrypt_pair(
            &keys.private_scalar,
            &ct.c1,
            &ct.c2,
            &keys.generator,
            &table,
        )
        .expect("decrypt pair");
        assert_eq!(dec, et["decrypted"].as_i64().expect("decrypted"));
    }
}
