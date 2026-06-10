//! Random linear combination helpers (paper Eq. 9 / 10; verifier **γ**, **γ′**).
//!
//! Replaces the reference Python `pf(secret_key, i)` / `rLCL` / `rLCR` self-check with
//! `γ^i` coefficients from `ClientChallenge` (soundness-oriented verifier randomness).

use libspartan::scalar::Scalar;

use crate::curve::embed_u128_to_scalar;

/// Powers `γ^0, …, γ^{n-1}`.
pub fn gamma_powers(gamma: &Scalar, n: usize) -> Vec<Scalar> {
    let mut out = Vec::with_capacity(n);
    let mut pow = Scalar::one();
    for _ in 0..n {
        out.push(pow);
        pow *= gamma;
    }
    out
}

/// Σ_i γ^i · v_i (scalar field; values embedded per `embed_u128_to_scalar`).
pub fn fold_rlc(values: &[u128], gamma: &Scalar) -> Scalar {
    let mut acc = Scalar::zero();
    let mut pow = Scalar::one();
    for &v in values {
        acc += pow * embed_u128_to_scalar(v);
        pow *= gamma;
    }
    acc
}

/// Dot product Σ_k f[k] · c[k] (paper Eq. 6 / (5) per window).
pub fn mac_filter_window(filter: &[u128], window: &[u128]) -> Scalar {
    let k = filter.len().min(window.len());
    let mut acc = Scalar::zero();
    for i in 0..k {
        acc += embed_u128_to_scalar(filter[i]) * embed_u128_to_scalar(window[i]);
    }
    acc
}

/// Paper Eq. (9) right-hand side (scalar form): Σ_i γ^i · MAC(f, window_i).
pub fn conv_rlc_right(filter: &[u128], windows: &[Vec<u128>], gamma: &Scalar) -> Scalar {
    let mut acc = Scalar::zero();
    let mut pow = Scalar::one();
    for window in windows {
        acc += pow * mac_filter_window(filter, window);
        pow *= gamma;
    }
    acc
}

/// Paper Eq. (9) left-hand side: Σ_i γ^i · â[i] (flattened convolution outputs).
pub fn conv_rlc_left(outputs: &[u128], gamma: &Scalar) -> Scalar {
    fold_rlc(outputs, gamma)
}

/// FC Eq. (10) left: Σ_j γ′^j · t[j] (outputs after bias).
pub fn fc_rlc_left(outputs: &[u128], gamma_prime: &Scalar) -> Scalar {
    fold_rlc(outputs, gamma_prime)
}

/// FC Eq. (10) right (matches `Server.py` `rLCR` type=1 in scalar field):
/// Σ_k d[k] · (Σ_i γ′^i · W[k,i]) + Σ_j γ′^j · b[j].
pub fn fc_rlc_right(
    inputs: &[u128],
    weights_in_out: &[Vec<u128>],
    bias: &[u128],
    gamma_prime: &Scalar,
) -> Scalar {
    let mut acc = Scalar::zero();
    for (k, row) in weights_in_out.iter().enumerate() {
        let mut w_rlc = Scalar::zero();
        let mut pow = Scalar::one();
        for &w in row {
            w_rlc += pow * embed_u128_to_scalar(w);
            pow *= gamma_prime;
        }
        let d = inputs.get(k).copied().unwrap_or(0);
        acc += embed_u128_to_scalar(d) * w_rlc;
    }
    acc + fold_rlc(bias, gamma_prime)
}
