"""Random linear combination helpers (paper Eq. 9 / 10; port of layer_proof/rlc.rs)."""

from __future__ import annotations

# Ristretto255 / Ed25519 scalar field (E1), matches cp-snark-full curve.rs
E1_FIELD_MODULUS = int(
    "1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed", 16
)

Scalar = int


def _mod(x: int) -> Scalar:
    return x % E1_FIELD_MODULUS


def embed_u128_to_scalar(value: int) -> Scalar:
    """Canonical u128 → scalar (16-byte LE in low half of 64-byte wide buffer, mod q_1)."""
    if value < 0 or value >= 2**128:
        raise ValueError("value must fit in u128")
    wide = bytearray(64)
    wide[:16] = value.to_bytes(16, "little")
    return _mod(int.from_bytes(wide, "little"))


def scalar_from_hex(h: str) -> Scalar:
    """Map 32-byte hex to scalar via from_bytes_wide semantics."""
    raw = bytes.fromhex(h)
    wide = bytearray(64)
    wide[: min(len(raw), 64)] = raw[: min(len(raw), 64)]
    return _mod(int.from_bytes(wide, "little"))


def gamma_powers(gamma: Scalar, n: int) -> list[Scalar]:
    out: list[Scalar] = []
    pow_val = 1
    for _ in range(n):
        out.append(pow_val)
        pow_val = _mod(pow_val * gamma)
    return out


def fold_rlc(values: list[int], gamma: Scalar) -> Scalar:
    """Σ_i γ^i · embed(v_i) — paper RLC fold."""
    acc = 0
    pow_val = 1
    for v in values:
        acc = _mod(acc + pow_val * embed_u128_to_scalar(v))
        pow_val = _mod(pow_val * gamma)
    return acc


def mac_filter_window(filter_flat: list[int], window: list[int]) -> Scalar:
    """Dot product Σ_k filter[k] · window[k] (paper Eq. 5 / 6 per window)."""
    k = min(len(filter_flat), len(window))
    acc = 0
    for i in range(k):
        acc = _mod(
            acc
            + embed_u128_to_scalar(filter_flat[i]) * embed_u128_to_scalar(window[i])
        )
    return acc


def conv_rlc_right(
    filter_flat: list[int], windows: list[list[int]], gamma: Scalar
) -> Scalar:
    """Paper Eq. (9) RHS: Σ_i γ^i · MAC(f, window_i)."""
    acc = 0
    pow_val = 1
    for window in windows:
        acc = _mod(acc + pow_val * mac_filter_window(filter_flat, window))
        pow_val = _mod(pow_val * gamma)
    return acc


def conv_rlc_left(outputs: list[int], gamma: Scalar) -> Scalar:
    """Paper Eq. (9) LHS: Σ_i γ^i · â[i]."""
    return fold_rlc(outputs, gamma)


def fc_rlc_left(outputs: list[int], gamma_prime: Scalar) -> Scalar:
    """FC Eq. (10) LHS: Σ_j γ′^j · t[j]."""
    return fold_rlc(outputs, gamma_prime)


def fc_rlc_right(
    inputs: list[int],
    weights_in_out: list[list[int]],
    bias: list[int],
    gamma_prime: Scalar,
) -> Scalar:
    """FC Eq. (10) RHS: Σ_k d[k]·(Σ_i γ′^i·W[k,i]) + Σ_j γ′^j·b[j]."""
    acc = 0
    for k, row in enumerate(weights_in_out):
        w_rlc = 0
        pow_val = 1
        for w in row:
            w_rlc = _mod(w_rlc + pow_val * embed_u128_to_scalar(w))
            pow_val = _mod(pow_val * gamma_prime)
        d = inputs[k] if k < len(inputs) else 0
        acc = _mod(acc + embed_u128_to_scalar(d) * w_rlc)
    return _mod(acc + fold_rlc(bias, gamma_prime))
