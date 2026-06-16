"""Server-side P0–P6 session state machine (platform architecture §4)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from vpin_backend.protocol.messages import (
    ClientChallenge,
    InferenceComplete,
    InputCommitment,
    ModelCommitment,
    ModelSelect,
    ProofBundle,
    SessionAccept,
    SessionStart,
)


class SessionPhase(str, Enum):
    INIT = "init"
    READY = "ready"
    MODEL_BOUND = "model_bound"
    INPUT_COMMITTED = "input_committed"
    INFERENCE = "inference"
    INFERENCE_DONE = "inference_done"
    CHALLENGE_RECEIVED = "challenge_received"
    PROOF_SENT = "proof_sent"
    CLOSED = "closed"


class ServerSessionState(BaseModel):
    session_id: str
    phase: SessionPhase = SessionPhase.INIT
    client_version: str = ""
    model_id: str = ""
    network_id: str = "A"
    model_commitment: Optional[ModelCommitment] = None
    input_commitment: Optional[InputCommitment] = None
    inference: Optional[InferenceComplete] = None
    client_challenge: Optional[ClientChallenge] = None
    proof_bundle: Optional[ProofBundle] = None
    errors: list[str] = Field(default_factory=list)

    def accept(self, msg: SessionStart) -> SessionAccept:
        self.client_version = msg.client_version
        self.phase = SessionPhase.READY
        return SessionAccept(
            session_id=self.session_id,
            server_version="vpin-backend/0.1.0",
            model_catalog_epoch="0",
        )

    def bind_model(self, msg: ModelSelect, commitment: ModelCommitment, network_id: str = "A") -> ModelCommitment:
        if self.phase not in (SessionPhase.READY, SessionPhase.MODEL_BOUND):
            raise ValueError(f"cannot bind model in phase {self.phase}")
        self.model_id = msg.model_id
        self.network_id = network_id
        self.model_commitment = commitment
        self.phase = SessionPhase.MODEL_BOUND
        return commitment

    def commit_input(self, msg: InputCommitment) -> None:
        if self.phase != SessionPhase.MODEL_BOUND:
            raise ValueError(f"cannot commit input in phase {self.phase}")
        self.input_commitment = msg
        self.phase = SessionPhase.INPUT_COMMITTED

    def start_inference(self) -> None:
        if self.phase != SessionPhase.INPUT_COMMITTED:
            raise ValueError(f"cannot start inference in phase {self.phase}")
        self.phase = SessionPhase.INFERENCE

    def complete_inference(self, msg: InferenceComplete) -> InferenceComplete:
        if self.phase != SessionPhase.INFERENCE:
            raise ValueError(f"cannot complete inference in phase {self.phase}")
        self.inference = msg
        self.phase = SessionPhase.INFERENCE_DONE
        return msg

    def receive_challenge(self, msg: ClientChallenge) -> None:
        if self.phase != SessionPhase.INFERENCE_DONE:
            raise ValueError(f"cannot receive challenge in phase {self.phase}")
        if not msg.gamma:
            raise ValueError("client gamma required — server must not sample γ")
        self.client_challenge = msg
        self.phase = SessionPhase.CHALLENGE_RECEIVED

    def attach_proof(self, bundle: ProofBundle) -> ProofBundle:
        if self.phase != SessionPhase.CHALLENGE_RECEIVED:
            raise ValueError(f"cannot attach proof in phase {self.phase}")
        self.proof_bundle = bundle
        self.phase = SessionPhase.PROOF_SENT
        return bundle

    def close(self) -> None:
        self.phase = SessionPhase.CLOSED
