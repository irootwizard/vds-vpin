//! Wire-compatible point conversion between ark and ec stacks.

use ahe_crypto_e2::E2Point;
use ahe_crypto_e2_ec::{ec_point_from_coords_be, EcE2Point};

pub fn ec_to_ark(p: &EcE2Point) -> E2Point {
    let (x, y) = p.lookup_key();
    if x == [0u8; 32] && y == [0u8; 32] {
        E2Point::Identity
    } else {
        E2Point::Affine { x, y }
    }
}

pub fn ark_to_ec(p: &E2Point) -> EcE2Point {
    match p {
        E2Point::Identity => EcE2Point::Identity,
        E2Point::Affine { x, y } => ec_point_from_coords_be(*x, *y),
    }
}

pub fn ec_tensor4_to_ark(t: Vec<Vec<Vec<Vec<EcE2Point>>>>) -> Vec<Vec<Vec<Vec<E2Point>>>> {
    t.into_iter()
        .map(|b| {
            b.into_iter()
                .map(|c| {
                    c.into_iter()
                        .map(|r| r.into_iter().map(|p| ec_to_ark(&p)).collect())
                        .collect()
                })
                .collect()
        })
        .collect()
}

pub fn ec_grid2_to_ark(t: Vec<Vec<EcE2Point>>) -> Vec<Vec<E2Point>> {
    t.into_iter()
        .map(|row| row.into_iter().map(|p| ec_to_ark(&p)).collect())
        .collect()
}

pub fn ark_tensor4_to_ec(t: Vec<Vec<Vec<Vec<E2Point>>>>) -> Vec<Vec<Vec<Vec<EcE2Point>>>> {
    t.into_iter()
        .map(|b| {
            b.into_iter()
                .map(|c| {
                    c.into_iter()
                        .map(|r| r.into_iter().map(|p| ark_to_ec(&p)).collect())
                        .collect()
                })
                .collect()
        })
        .collect()
}

pub fn ark_grid2_to_ec(t: Vec<Vec<E2Point>>) -> Vec<Vec<EcE2Point>> {
    t.into_iter()
        .map(|row| row.into_iter().map(|p| ark_to_ec(&p)).collect())
        .collect()
}
