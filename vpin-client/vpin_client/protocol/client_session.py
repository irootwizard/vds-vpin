"""Client-side session state machine skeleton (P2 / P4 / P6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from vpin_client.protocol.messages import (
    ClientChallenge,
    InferenceComplete,
    InputCommitment,
    ModelCommitment,
    ProofBundle,
    SessionAccept,
    VerificationReport,
)


class ClientSessionState(Enum):
    IDLE = auto()
    SESSION_ACCEPTED = auto()
    MODEL_BOUND = auto()
    INPUT_COMMITTED = auto()
    INFERENCE_DONE = auto()
    CHALLENGE_SENT = auto()
    PROOF_RECEIVED = auto()
    VERIFIED = auto()


@dataclass
class ClientSession:
    """Tracks client protocol progress; verify logic wired in later sprints."""

    session_id: Optional[str] = None
    state: ClientSessionState = ClientSessionState.IDLE
    model_commitment: Optional[ModelCommitment] = None
    input_commitment: Optional[InputCommitment] = None
    inference: Optional[InferenceComplete] = None
    challenge: Optional[ClientChallenge] = None
    proof_bundle: Optional[ProofBundle] = None
    verification_report: Optional[VerificationReport] = None
    _pending_cm_x: str = field(default="", repr=False)

    def on_session_accept(self, accept: SessionAccept) -> None:
        self.session_id = accept.session_id
        self.state = ClientSessionState.SESSION_ACCEPTED

    def on_model_commitment(self, commitment: ModelCommitment) -> None:
        self.model_commitment = commitment
        self.state = ClientSessionState.MODEL_BOUND

    def prepare_input_commitment(self, cm_x: str, ciphertext_meta: dict | None = None) -> InputCommitment:
        msg = InputCommitment(cm_x=cm_x, ciphertext_meta=ciphertext_meta or {})
        self._pending_cm_x = cm_x
        return msg

    def mark_input_committed(self) -> None:
        if self._pending_cm_x:
            self.input_commitment = InputCommitment(cm_x=self._pending_cm_x)
        self.state = ClientSessionState.INPUT_COMMITTED

    def on_inference_complete(self, complete: InferenceComplete) -> None:
        self.inference = complete
        self.state = ClientSessionState.INFERENCE_DONE

    def build_challenge(self) -> ClientChallenge:
        from vpin_client.crypto.challenge import sample_challenge

        if self.inference is None:
            raise RuntimeError("inference stats required before P4 challenge")
        ch = sample_challenge(self.inference.num_pt_add, self.inference.num_pt_mult)
        self.challenge = ch
        self.state = ClientSessionState.CHALLENGE_SENT
        return ch

    def on_proof_bundle(self, bundle: ProofBundle) -> None:
        self.proof_bundle = bundle
        self.state = ClientSessionState.PROOF_RECEIVED

    def mark_verified(self, ok: bool, detail: str = "") -> VerificationReport:
        report = VerificationReport(
            session_id=self.session_id or "",
            ok=ok,
            cm_w=self.model_commitment.cm_w if self.model_commitment else "",
            cm_x=self.input_commitment.cm_x if self.input_commitment else "",
            gamma_prefix=(self.challenge.gamma[:16] if self.challenge else ""),
            proof_coverage=self.proof_bundle.proof_coverage if self.proof_bundle else "",
            detail=detail,
        )
        self.verification_report = report
        self.state = ClientSessionState.VERIFIED
        return report
