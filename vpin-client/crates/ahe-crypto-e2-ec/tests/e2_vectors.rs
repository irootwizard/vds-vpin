use std::path::PathBuf;

use ahe_crypto_e2_ec::{
    be32_to_coord, coord_to_be32, decrypt_pair, encrypt_scalar_with_r, EcE2Point, EcKeyMaterial,
    BsgsTable,
};
use num_bigint::BigUint;
use serde_json::Value;

fn fixture_paths() -> (PathBuf, PathBuf) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures");
    (root.join("e2_vectors.json"), root.join("table.bin"))
}

fn parse_private_scalar(raw: &str) -> BigUint {
    let key = "\"private_scalar\":";
    let tail = raw.split(key).nth(1).expect("private scalar key");
    let digits = tail.split(',').next().expect("private scalar value").trim();
    BigUint::parse_bytes(digits.as_bytes(), 10).expect("parse private scalar")
}

fn decimal_to_be32(s: &str) -> [u8; 32] {
    coord_to_be32(&BigUint::parse_bytes(s.as_bytes(), 10).expect("decimal"))
}

#[test]
fn ec_matches_e2_vectors_fixture() {
    let (vector_path, table_path) = fixture_paths();
    let raw = std::fs::read_to_string(&vector_path).expect("read e2_vectors");
    let v: Value = serde_json::from_str(&raw).expect("parse");

    let sk = parse_private_scalar(&raw);
    let keys = EcKeyMaterial::key_gen_deterministic(sk.clone());

    // public key
    assert_point_decimal(
        &keys.public_key,
        v["public_key_x"].as_str().unwrap(),
        v["public_key_y"].as_str().unwrap(),
        "public_key",
    );

    // G * 1
    let g1 = keys.generator.scalar_mul(&BigUint::from(1u32));
    assert_point_decimal(
        &g1,
        v["point_ops"]["g_times_1_x"].as_str().unwrap(),
        v["point_ops"]["g_times_1_y"].as_str().unwrap(),
        "g_times_1",
    );

    // sk * G
    assert_point_decimal(
        &keys.public_key,
        v["point_ops"]["sk_times_g_x"].as_str().unwrap(),
        v["point_ops"]["sk_times_g_y"].as_str().unwrap(),
        "sk_times_g",
    );

    let et = &v["encrypt_test"];
    let plaintext = et["plaintext"].as_i64().expect("plaintext");
    let r = BigUint::from(et["r"].as_u64().expect("r"));
    let order = keys.curve_order.clone();

    let ct = encrypt_scalar_with_r(
        plaintext,
        &keys.generator,
        &keys.public_key,
        &r,
        &order,
    );

    assert_point_decimal(
        &ct.c1,
        et["c1_x"].as_str().unwrap(),
        et["c1_y"].as_str().unwrap(),
        "c1",
    );
    assert_point_decimal(
        &ct.c2,
        et["c2_x"].as_str().unwrap(),
        et["c2_y"].as_str().unwrap(),
        "c2",
    );

    if table_path.is_file() {
        let table = BsgsTable::load(&table_path).expect("load table");
        let dec = decrypt_pair(
            &keys.private_scalar,
            &ct.c1,
            &ct.c2,
            &keys.generator,
            &table,
        )
        .expect("decrypt");
        assert_eq!(dec, plaintext);
    }
}

fn assert_point_decimal(p: &EcE2Point, x_dec: &str, y_dec: &str, label: &str) {
    let expected_x = decimal_to_be32(x_dec);
    let expected_y = decimal_to_be32(y_dec);
    match p {
        EcE2Point::Identity => panic!("{label}: unexpected identity"),
        EcE2Point::Affine { x, y, .. } => {
            assert_eq!(*x, expected_x, "{label} x");
            assert_eq!(*y, expected_y, "{label} y");
            assert_eq!(be32_to_coord(x), BigUint::parse_bytes(x_dec.as_bytes(), 10).unwrap());
        }
    }
}

#[test]
fn micro_bench_encrypt_decrypt() {
    let (_, table_path) = fixture_paths();
    if !table_path.is_file() {
        return;
    }
    let table = BsgsTable::load(&table_path).expect("load table");
    let sk = BigUint::from(12345u64);
    let keys = EcKeyMaterial::key_gen_deterministic(sk);
    let r = BigUint::from(999u64);
    let order = keys.curve_order.clone();

    let n = 50;
    let t0 = std::time::Instant::now();
    for _ in 0..n {
        let ct = encrypt_scalar_with_r(42, &keys.generator, &keys.public_key, &r, &order);
        let _ = decrypt_pair(
            &keys.private_scalar,
            &ct.c1,
            &ct.c2,
            &keys.generator,
            &table,
        )
        .expect("dec");
    }
    let ec_ms = t0.elapsed().as_secs_f64() * 1000.0;
    eprintln!("ec {n}x enc+dec: {ec_ms:.1} ms ({:.2} ms/op)", ec_ms / n as f64);
}
