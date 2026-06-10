"""ClientChallenge sampling — CSPRNG γ / γ_add / γ_mult (P4, client-only)."""

from __future__ import annotations

import secrets

from vpin_client.protocol.messages import ClientChallenge

_SCALAR_HEX_LEN = 64  # 32 bytes


def _random_scalar_hex() -> str:
    return secrets.token_hex(32)


def sample_challenge(num_pt_add: int, num_pt_mult: int) -> ClientChallenge:
    """Sample verifier randomness before server prove (platform §4.4)."""
    return ClientChallenge(
        gamma=_random_scalar_hex(),
        gamma_add=_random_scalar_hex(),
        gamma_mult=_random_scalar_hex(),
        num_pt_add=num_pt_add,
        num_pt_mult=num_pt_mult,
    )


def challenge_from_hex(
    gamma: str,
    gamma_add: str,
    gamma_mult: str,
    num_pt_add: int,
    num_pt_mult: int,
) -> ClientChallenge:
    """Deterministic challenge for tests (not for production)."""
    for label, h in (
        ("gamma", gamma),
        ("gamma_add", gamma_add),
        ("gamma_mult", gamma_mult),
    ):
        if len(h) != _SCALAR_HEX_LEN or any(c not in "0123456789abcdef" for c in h.lower()):
            raise ValueError(f"{label} must be 64 hex chars")
    return ClientChallenge(
        gamma=gamma.lower(),
        gamma_add=gamma_add.lower(),
        gamma_mult=gamma_mult.lower(),
        num_pt_add=num_pt_add,
        num_pt_mult=num_pt_mult,
    )
