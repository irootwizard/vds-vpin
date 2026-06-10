"""P0–P6 protocol message types (platform architecture §4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProofCoverage = Literal[
    "ec_gadget_only",
    "ec_plus_scalar_check",
    "ec_plus_l1_binding",
    "skeleton_ec_stub",
]


class SessionStart(BaseModel):
    """R0: client opens TLS session."""

    client_version: str
    ahe_params_id: str = "e2-default"


class SessionAccept(BaseModel):
    session_id: str
    server_version: str
    model_catalog_epoch: str


class ModelSelect(BaseModel):
    model_id: str


class TruncationPhase(BaseModel):
    phase_id: str
    layer: str | None = None
    bits: int


class TruncationPlan(BaseModel):
    phases: list[TruncationPhase] = Field(default_factory=list)


class PedersenCommitment(BaseModel):
    point_hex: str
    digest_hex: str


class CurveE2Meta(BaseModel):
    curve_base_field: str
    a: str
    b: str
    generator_x: str
    generator_y: str
    curve_order: str


class ModelCommitment(BaseModel):
    """P1: server → client model binding."""

    cm_W: PedersenCommitment = Field(alias="cm_W")
    e2_digest: str | None = None
    topology_hash: str
    truncation_plan: TruncationPlan | None = None
    num_weights: int | None = None
    curve_e2: CurveE2Meta | None = None

    model_config = {"populate_by_name": True}


class InputCommitment(BaseModel):
    """P2: client → server input binding."""

    cm_x: PedersenCommitment = Field(alias="cm_x")
    ciphertext_meta: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class PublicKey(BaseModel):
    """P3: client ephemeral AHE public key."""

    h: str
    curve_meta: CurveE2Meta | None = None


class CiphertextChunkMeta(BaseModel):
    phase_id: str
    chunk_index: int
    byte_length: int
    encoding: str = "bincode"


class TruncateRequest(BaseModel):
    """P3 loop: server asks client to decrypt/truncate/re-encrypt."""

    phase_id: str
    bits: int
    shape: list[int]


class InferenceComplete(BaseModel):
    """P3 end: homomorphic inference finished."""

    num_pt_add: int
    num_pt_mult: int
    witness_root: str | None = None


class ClientChallenge(BaseModel):
    """P4: client-only random challenge (γ)."""

    gamma: str
    gamma_add: str
    gamma_mult: str
    num_pt_add: int
    num_pt_mult: int


class SubCircuitProof(BaseModel):
    circuit_name: str
    proof_bytes_hex: str | None = None
    num_cons: int = 0
    num_vars: int = 0


class ProofBundle(BaseModel):
    """P5: server proof response."""

    pi_add: SubCircuitProof | None = None
    pi_mult: SubCircuitProof | None = None
    rlc_binding: str
    proof_coverage: ProofCoverage | str = "skeleton_ec_stub"
    prove_time_ms: int
    trace_digest: str | None = None


class VerificationReport(BaseModel):
    """P6 optional audit report."""

    session_id: str
    ok: bool
    cm_W: str
    cm_x: str
    gamma_prefix: str
    proof_coverage: ProofCoverage | str
    message: str | None = None

    model_config = {"populate_by_name": True}
