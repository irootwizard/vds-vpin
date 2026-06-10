"""P0–P6 protocol message types and client session state."""

from .messages import (
    ClientChallenge,
    InferenceComplete,
    InputCommitment,
    ModelCommitment,
    ModelSelect,
    ProofBundle,
    SessionAccept,
    SessionStart,
    VerificationReport,
)

__all__ = [
    "ClientChallenge",
    "ClientSession",
    "ClientSessionState",
    "InferenceComplete",
    "InputCommitment",
    "ModelCommitment",
    "ModelSelect",
    "ProofBundle",
    "SessionAccept",
    "SessionStart",
    "VerificationReport",
]


def __getattr__(name: str):
    if name in ("ClientSession", "ClientSessionState"):
        from .client_session import ClientSession, ClientSessionState

        return ClientSession if name == "ClientSession" else ClientSessionState
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
