"""Server-side prove / setup input contracts (plan §1.1 ServerProveInput)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from vpin_backend.protocol.messages import (
    ClientChallenge,
    InputCommitment,
    ModelCommitment,
    PedersenCommitment,
)


class ModelOpening(BaseModel):
    weights: list[str]
    blind_hex: str


class InputOpening(BaseModel):
    public_scalars_hex: list[str]
    blind_hex: str


class TraceBundle(BaseModel):
    conv_trace: Path | None = None
    pool_trace: Path | None = None
    fc_trace: Path | None = None


class ModelCommitmentBundle(BaseModel):
    """Rust-compatible bundle wrapper."""

    cm_weights: PedersenCommitment
    num_weights: int
    e2_digest_hex: str
    curve_e2: dict[str, str]


class InputCommitmentBundle(BaseModel):
    cm_public: PedersenCommitment
    num_public_inputs: int


class ServerProveInput(BaseModel):
    """P4 → P5 server prove bus input."""

    network_id: str
    challenge: ClientChallenge
    cm_w: ModelCommitmentBundle
    cm_x: InputCommitmentBundle
    model_opening: ModelOpening
    trace_bundle: TraceBundle = Field(default_factory=TraceBundle)
    ec_witness_root: Path | None = None
    input_opening: InputOpening | None = None


class ChallengePayload(BaseModel):
    """Wire payload for prove-with-challenge CLI."""

    challenge: ClientChallenge


class ProveRequest(BaseModel):
    session_id: str
    network_id: str
    challenge: ClientChallenge
    setup_artifact: Path | None = None
    run_dir: Path | None = None
    model_id: str | None = None
    schedule_mode: str = "paper_proof"
    model_id: str | None = None
    run_dir: Path | None = None


class SetupRequest(BaseModel):
    network_id: str
    weights_path: Path | None = None


class SetupResponse(BaseModel):
    network_id: str
    model_commitment: ModelCommitment
    input_commitment: InputCommitment
    setup_path: Path
