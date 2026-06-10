"""Minimal P0–P6 message types (mirror backend / platform §4 schema)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SessionStart:
    client_version: str
    ahe_params_id: str


@dataclass
class SessionAccept:
    session_id: str
    server_version: str
    model_catalog_epoch: str


@dataclass
class ModelSelect:
    model_id: str


@dataclass
class ModelCommitment:
    cm_w: str
    e2_digest: str = ""
    topology_hash: str = ""
    truncation_plan: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class InputCommitment:
    cm_x: str
    ciphertext_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceComplete:
    num_pt_add: int
    num_pt_mult: int
    witness_root: Optional[str] = None


@dataclass
class ClientChallenge:
    """P4 challenge — γ sampled only on client (CSPRNG)."""

    gamma: str
    gamma_add: str
    gamma_mult: str
    num_pt_add: int
    num_pt_mult: int


@dataclass
class ProofBundle:
    pi_add: Optional[str] = None
    pi_mult: Optional[str] = None
    rlc_binding: Optional[str] = None
    prove_time_ms: Optional[int] = None
    proof_coverage: str = "ec_gadget_only"
    trace_digest: Optional[str] = None


@dataclass
class VerificationReport:
    session_id: str
    ok: bool
    cm_w: str = ""
    cm_x: str = ""
    gamma_prefix: str = ""
    proof_coverage: str = ""
    detail: str = ""
