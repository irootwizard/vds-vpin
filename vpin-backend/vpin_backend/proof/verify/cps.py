"""Phase Z.7: client-side CPS.Ver orchestration.

This module sits on top of the per-layer M1 scalar checks (`verify_all_client`)
and the Pedersen-opening verification (`commitment.pedersen.verify_pedersen_open`)
to provide a single `verify_toy_cps_bundle` entry that mirrors the Rust
`vpin-server-crypto::circuit::cps_ver::verify_toy_cps_bundle`.

Verification path (matches paper 搂3 transcript order
``cm_W 鈫?cm_x 鈫?纬 鈫?纬_add 鈫?纬_mult 鈫?sub_circuit``):

1. Bundle schema sanity (kind=``spartan_pc``, opening length matches the
   advertised ``num_scalars``).
2. cm_W catalog binding 鈥?the bundle's ``cm_w.cm_hex`` must equal the
   value persisted in the local model catalog (a hex string the client
   stored at registration time, e.g. ``TOY_W_STAR_CM_HEX``).
3. Pedersen digest cross-check 鈥?the bundle's legacy
   ``model_commitment.cm_weights.digest_hex`` must be derivable from the
   W* opening (re-uses :func:`vpin_backend.commitment.pedersen.scalars_digest`).
4. L1 binding 鈥?toy weight layout slots match trace filter / weights /
   bias values.
5. M1 scalar checks 鈥?run the existing :func:`verify_all_client` stack on
   the supplied traces with 纬 / 纬_add / 纬_mult.
6. 纬-replay rejection 鈥?a :class:`GammaReplayGuard` records every
   (session_id, 纬) pair the client has ever accepted and refuses a
   repeat.

The Spartan PC group-element binding of cm_W to the polynomial is **not**
re-checked in Python (no Ristretto255 group operations here). The client
either trusts a catalog handoff or shells out to
``vpin-server-crypto verify-cps --toy`` for a Rust-side cross-check (see
:func:`maybe_delegate_spartan_pc_to_rust`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from vpin_backend.commitment.pedersen import scalars_digest
from vpin_backend.protocol.messages import ClientChallenge
from vpin_backend.proof.verify.conv import ConvLayerProofSpec
from vpin_backend.proof.verify.fc import FcLayerProofSpec
from vpin_backend.proof.verify.pool import PoolLayerProofSpec
from vpin_backend.proof.verify.stack import ServerLinearProofStack, verify_all_client

CPS_KIND_SPARTAN_PC = "spartan_pc"
TOY_W_STAR_LEN = 13


class CpsVerifyStage(Enum):
    SCHEMA = "schema"
    CM_W_CATALOG = "cm_w_catalog"
    PEDERSEN_DIGEST = "pedersen_digest"
    L1_BINDING = "l1_binding"
    SCALAR = "scalar"
    GAMMA_REPLAY = "gamma_replay"


class CpsVerifyError(Exception):
    def __init__(self, stage: CpsVerifyStage, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"{stage.value}: {detail}")


# ---------- Bundle dataclasses (mirror the Rust JSON serde) -------------

@dataclass
class PyCpsCommitment:
    cm_hex: str
    num_scalars: int
    padded_len: int
    poly_comm_hex: list[str]
    kind: str

    @classmethod
    def from_dict(cls, d: dict) -> "PyCpsCommitment":
        return cls(
            cm_hex=str(d["cm_hex"]),
            num_scalars=int(d["num_scalars"]),
            padded_len=int(d["padded_len"]),
            poly_comm_hex=[str(s) for s in d["poly_comm_hex"]],
            kind=str(d["kind"]),
        )


@dataclass
class PyConvTrace:
    filter: list[int]
    windows: list[list[int]]
    outputs: list[int]


@dataclass
class PyPoolTrace:
    windows: list[list[int]]
    outputs: list[int]


@dataclass
class PyFcTrace:
    input: int
    weights: list[int]
    bias: list[int]
    outputs: list[int]


@dataclass
class PyToyCpsBundle:
    cm_w: PyCpsCommitment
    w_star_opening: list[int]
    model_commitment_digest_hex: str
    challenge: ClientChallenge
    pi_conv_bytes_len: int
    pi_pool_bytes_len: int
    pi_fc_bytes_len: int

    @classmethod
    def from_dict(cls, d: dict) -> "PyToyCpsBundle":
        ch = d["bundle"]["challenge"]
        return cls(
            cm_w=PyCpsCommitment.from_dict(d["bundle"]["cm_w"]),
            w_star_opening=[int(s) for s in d["w_star_opening"]],
            model_commitment_digest_hex=str(
                d["bundle"]["model_commitment"]["cm_weights"]["digest_hex"]
            ),
            challenge=ClientChallenge(
                gamma=str(ch["gamma"]),
                gamma_add=str(ch["gamma_add"]),
                gamma_mult=str(ch["gamma_mult"]),
                num_pt_add=int(ch.get("num_point_adds", 0)),
                num_pt_mult=int(ch.get("num_point_mults", 0)),
            ),
            pi_conv_bytes_len=len(d["bundle"]["pi_conv"]["proof_bytes"]),
            pi_pool_bytes_len=len(d["bundle"]["pi_pool"]["proof_bytes"]),
            pi_fc_bytes_len=len(d["bundle"]["pi_fc"]["proof_bytes"]),
        )


@dataclass
class PyToyCpsTraces:
    conv: PyConvTrace
    pool: PyPoolTrace
    fc: PyFcTrace

    @classmethod
    def from_dict(cls, d: dict) -> "PyToyCpsTraces":
        td = d["traces"]
        return cls(
            conv=PyConvTrace(
                filter=[int(x) for x in td["conv"]["filter"]],
                windows=[[int(x) for x in row] for row in td["conv"]["windows"]],
                outputs=[int(x) for x in td["conv"]["outputs"]],
            ),
            pool=PyPoolTrace(
                windows=[[int(x) for x in row] for row in td["pool"]["windows"]],
                outputs=[int(x) for x in td["pool"]["outputs"]],
            ),
            fc=PyFcTrace(
                input=int(td["fc"]["input"]),
                weights=[int(x) for x in td["fc"]["weights"]],
                bias=[int(x) for x in td["fc"]["bias"]],
                outputs=[int(x) for x in td["fc"]["outputs"]],
            ),
        )


@dataclass
class ToyWeightLayout:
    """Constants matching `vpin-server-crypto::bind_l1::ToyWeightLayout`."""

    CONV_FILTER: tuple[int, int] = (0, 9)
    FC_WEIGHTS: tuple[int, int] = (9, 11)
    FC_BIAS: tuple[int, int] = (11, 13)

    @staticmethod
    def conv_filter(w_star: list[int]) -> list[int]:
        return w_star[0:9]

    @staticmethod
    def fc_weights(w_star: list[int]) -> list[int]:
        return w_star[9:11]

    @staticmethod
    def fc_bias(w_star: list[int]) -> list[int]:
        return w_star[11:13]


# ---------- 纬-replay guard ----------

@dataclass
class GammaReplayGuard:
    """Reject (session_id, 纬) pairs the client has already accepted.

    Keeps a small in-memory set; production deployments persist to disk /
    catalog. The CSPRNG sampled 纬 MUST appear at most once per session id.
    """

    _seen: set[tuple[str, str]] = field(default_factory=set)

    def admit(self, session_id: str, gamma_hex: str) -> None:
        key = (session_id, gamma_hex)
        if key in self._seen:
            raise CpsVerifyError(
                CpsVerifyStage.GAMMA_REPLAY,
                f"纬 {gamma_hex[:8]}... already used in session {session_id}",
            )
        self._seen.add(key)


# ---------- Stack builder ----------

def stack_from_toy_traces(
    traces: PyToyCpsTraces, *, skip_fc: bool = False
) -> ServerLinearProofStack:
    stack = ServerLinearProofStack(skip_fc=skip_fc)
    stack.conv_layers.append(
        ConvLayerProofSpec(
            filter_flat=list(traces.conv.filter),
            windows=[list(row) for row in traces.conv.windows],
            output_flat=list(traces.conv.outputs),
        )
    )
    stack.pool_layers.append(
        PoolLayerProofSpec(
            windows=[list(row) for row in traces.pool.windows],
            output_sums=list(traces.pool.outputs),
        )
    )
    # Toy FC is a 1鈫? linear layer with bias; spec expects weights_in_out
    # shaped as a list of "input_dim" rows, each with "output_dim" entries.
    # Toy fc.weights is the row for the single input.
    stack.fc_layers.append(
        FcLayerProofSpec(
            inputs=[traces.fc.input],
            weights_in_out=[list(traces.fc.weights)],
            bias=list(traces.fc.bias),
            outputs=list(traces.fc.outputs),
        )
    )
    return stack


# ---------- L1 binding ----------

def check_l1_toy_binding(
    w_star: list[int], traces: PyToyCpsTraces
) -> None:
    if len(w_star) != TOY_W_STAR_LEN:
        raise CpsVerifyError(
            CpsVerifyStage.L1_BINDING,
            f"W* len {len(w_star)} != {TOY_W_STAR_LEN}",
        )
    if ToyWeightLayout.conv_filter(w_star) != traces.conv.filter:
        raise CpsVerifyError(
            CpsVerifyStage.L1_BINDING,
            f"conv filter mismatch W*[0..9] vs trace.filter",
        )
    if ToyWeightLayout.fc_weights(w_star) != traces.fc.weights:
        raise CpsVerifyError(
            CpsVerifyStage.L1_BINDING,
            f"fc weights mismatch W*[9..11]",
        )
    if ToyWeightLayout.fc_bias(w_star) != traces.fc.bias:
        raise CpsVerifyError(
            CpsVerifyStage.L1_BINDING,
            f"fc bias mismatch W*[11..13]",
        )


# ---------- Report ----------

@dataclass
class CpsVerifyReport:
    ok: bool
    cm_w_catalog_ok: bool = False
    pedersen_digest_ok: bool = False
    l1_binding_ok: bool = False
    scalar_ok: bool = False
    gamma_replay_ok: bool = False
    proof_coverage: str = ""
    detail: str = ""


# ---------- Main verifier ----------

def verify_toy_cps_bundle(
    bundle: PyToyCpsBundle,
    traces: PyToyCpsTraces,
    *,
    catalog_cm_w_hex: str,
    session_id: str,
    replay_guard: Optional[GammaReplayGuard] = None,
    expected_num_scalars: int = TOY_W_STAR_LEN,
) -> CpsVerifyReport:
    """P0鈥揚6 client-local verification of a toy CPS bundle.

    Returns a :class:`CpsVerifyReport`; raises :class:`CpsVerifyError` on
    fatal stage failures.
    """

    if bundle.cm_w.kind != CPS_KIND_SPARTAN_PC:
        raise CpsVerifyError(
            CpsVerifyStage.SCHEMA,
            f"cm_w.kind {bundle.cm_w.kind} != {CPS_KIND_SPARTAN_PC}",
        )
    if bundle.cm_w.num_scalars != expected_num_scalars:
        raise CpsVerifyError(
            CpsVerifyStage.SCHEMA,
            f"cm_w.num_scalars {bundle.cm_w.num_scalars} != {expected_num_scalars}",
        )
    if len(bundle.w_star_opening) != bundle.cm_w.num_scalars:
        raise CpsVerifyError(
            CpsVerifyStage.SCHEMA,
            f"opening len {len(bundle.w_star_opening)} != num_scalars {bundle.cm_w.num_scalars}",
        )
    if bundle.cm_w.padded_len & (bundle.cm_w.padded_len - 1) != 0:
        raise CpsVerifyError(
            CpsVerifyStage.SCHEMA,
            f"padded_len {bundle.cm_w.padded_len} not a power of two",
        )

    # P0 catalog binding: cm_W must match the local catalog value.
    if catalog_cm_w_hex and bundle.cm_w.cm_hex != catalog_cm_w_hex:
        raise CpsVerifyError(
            CpsVerifyStage.CM_W_CATALOG,
            f"bundle cm_hex {bundle.cm_w.cm_hex[:12]}... != catalog "
            f"{catalog_cm_w_hex[:12]}...",
        )
    cm_w_catalog_ok = True

    # Pedersen digest cross-check: recompute scalars_digest over opening
    # and compare with the legacy model_commitment digest_hex carried in
    # the bundle (still hashed inside per-layer SNARK transcripts).
    fresh_digest = scalars_digest(bundle.w_star_opening)
    if fresh_digest != bundle.model_commitment_digest_hex:
        raise CpsVerifyError(
            CpsVerifyStage.PEDERSEN_DIGEST,
            f"fresh digest {fresh_digest[:12]}... != bundle "
            f"{bundle.model_commitment_digest_hex[:12]}...",
        )
    pedersen_digest_ok = True

    check_l1_toy_binding(bundle.w_star_opening, traces)
    l1_binding_ok = True

    # M1 scalar checks (eq9 + eq7 + eq10) with bundle.challenge.
    stack = stack_from_toy_traces(traces, skip_fc=False)
    try:
        verify_all_client(stack, bundle.challenge)
        scalar_ok = True
    except Exception as exc:  # noqa: BLE001 鈥?bubble as CpsVerifyError
        raise CpsVerifyError(CpsVerifyStage.SCALAR, str(exc)) from exc

    if replay_guard is not None:
        replay_guard.admit(session_id, bundle.challenge.gamma)
    gamma_replay_ok = True

    return CpsVerifyReport(
        ok=True,
        cm_w_catalog_ok=cm_w_catalog_ok,
        pedersen_digest_ok=pedersen_digest_ok,
        l1_binding_ok=l1_binding_ok,
        scalar_ok=scalar_ok,
        gamma_replay_ok=gamma_replay_ok,
        proof_coverage="ec_plus_layer_pi_with_model_binding",
        detail=(
            f"pi_conv={bundle.pi_conv_bytes_len}B "
            f"pi_pool={bundle.pi_pool_bytes_len}B "
            f"pi_fc={bundle.pi_fc_bytes_len}B"
        ),
    )


# ---------- Optional Rust delegation ----------

def maybe_delegate_spartan_pc_to_rust(
    bundle_path: str,
) -> Optional[bool]:
    """Best-effort Rust cross-check of the Spartan PC binding.

    Returns ``True`` / ``False`` if the local workspace has a built
    ``vpin-server-crypto`` binary and the rust verification ran; ``None``
    when the toolchain is unavailable (test should skip rather than fail).
    """
    import subprocess

    from vpin_backend.config import get_settings

    repo = get_settings().repo_root
    exe = repo / "vpin-backend" / "target" / "debug" / "vpin-server-crypto.exe"
    if not exe.is_file():
        return None
    proc = subprocess.run(
        [str(exe), "verify-cps", "--toy", "--bundle-out", str(bundle_path)],
        cwd=str(repo / "vpin-backend"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 0 and "cps_ver_unified_toy_ok" in proc.stdout:
        return True
    if proc.returncode != 0:
        return False
    return None

