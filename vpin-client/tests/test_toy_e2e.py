"""Phase Z.7 client-local toy E2E (P0–P6) acceptance tests.

The Rust server-side prove + bundle dump is exercised via the
``vpin-server-crypto verify-cps --toy --bundle-out`` CLI; tests that need
the bundle are gated on the binary being present and skip otherwise.

Covers:

- Satisfiability: honest bundle → CpsVerifyReport.ok = True.
- Negative: tampered cm_W (catalog mismatch) → ``CM_W_CATALOG`` stage.
- Negative: tampered W* opening → Pedersen digest mismatch.
- Negative: tampered γ (in challenge) → scalar stage rejection
  (the Python M1 RLC fold differs from the trace fold).
- Negative: layout mismatch (fc weights tampered in traces) → L1 binding.
- Protocol: γ-replay rejected by ``GammaReplayGuard``.
- Protocol: bundle schema enforcement (kind, opening length, pow2 padding).
- Performance: writes ``vpin-backend/tests/perf/Z-7.json`` with the
  Python-side verify duration.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from vpin_client.protocol.messages import ClientChallenge
from vpin_client.verify.cps import (
    CPS_KIND_SPARTAN_PC,
    CpsVerifyError,
    CpsVerifyStage,
    GammaReplayGuard,
    PyToyCpsBundle,
    PyToyCpsTraces,
    TOY_W_STAR_LEN,
    verify_toy_cps_bundle,
)


# Frozen by vpin-server-crypto::tests::cps_toy_e2e::TOY_W_STAR_CM_HEX.
TOY_W_STAR_CM_HEX = "d056527f12aad5b2200a98e5e882c15d7dac17ed234ffa6352cd2e633b346645"


REPO = Path(__file__).resolve().parents[2]
RUST_BIN = REPO / "vpin-backend" / "target" / "debug" / "vpin-server-crypto.exe"
PERF_DIR = REPO / "vpin-backend" / "tests" / "perf"


def _have_rust_bin() -> bool:
    return RUST_BIN.is_file()


@pytest.fixture(scope="session")
def toy_bundle_path(tmp_path_factory) -> Path:
    """Dump the toy bundle JSON once per session via the Rust CLI."""
    if not _have_rust_bin():
        pytest.skip(
            "vpin-server-crypto binary not built; run "
            "`cargo build -p vpin-server-crypto --bin vpin-server-crypto` first"
        )
    out = tmp_path_factory.mktemp("z7") / "toy_bundle.json"
    proc = subprocess.run(
        [str(RUST_BIN), "verify-cps", "--toy", "--bundle-out", str(out)],
        cwd=str(REPO / "vpin-backend"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"verify-cps --toy failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "cps_ver_unified_toy_ok" in proc.stdout
    assert out.is_file()
    return out


@pytest.fixture
def bundle_doc(toy_bundle_path: Path) -> dict:
    return json.loads(toy_bundle_path.read_text(encoding="utf-8"))


@pytest.fixture
def bundle(bundle_doc: dict) -> PyToyCpsBundle:
    return PyToyCpsBundle.from_dict(bundle_doc)


@pytest.fixture
def traces(bundle_doc: dict) -> PyToyCpsTraces:
    return PyToyCpsTraces.from_dict(bundle_doc)


def _write_perf(verify_ms: int, bundle: PyToyCpsBundle) -> None:
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "Z-7",
        "verify_ms": verify_ms,
        "num_scalars": bundle.cm_w.num_scalars,
        "pi_total_bytes": (
            bundle.pi_conv_bytes_len
            + bundle.pi_pool_bytes_len
            + bundle.pi_fc_bytes_len
        ),
    }
    (PERF_DIR / "Z-7.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_p6_happy_path_and_perf(bundle: PyToyCpsBundle, traces: PyToyCpsTraces) -> None:
    """P6 honest path: every stage passes and ok=True."""
    guard = GammaReplayGuard()
    t0 = time.perf_counter()
    report = verify_toy_cps_bundle(
        bundle,
        traces,
        catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
        session_id="toy-session-1",
        replay_guard=guard,
    )
    verify_ms = int((time.perf_counter() - t0) * 1000)
    assert report.ok
    assert report.cm_w_catalog_ok
    assert report.pedersen_digest_ok
    assert report.l1_binding_ok
    assert report.scalar_ok
    assert report.gamma_replay_ok
    assert bundle.cm_w.kind == CPS_KIND_SPARTAN_PC
    assert bundle.cm_w.num_scalars == TOY_W_STAR_LEN
    _write_perf(verify_ms, bundle)


def test_p4_gamma_replay_rejected(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """P4: client refuses to admit the same γ twice in the same session."""
    guard = GammaReplayGuard()
    verify_toy_cps_bundle(
        bundle,
        traces,
        catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
        session_id="toy-replay",
        replay_guard=guard,
    )
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            bundle,
            traces,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-replay",
            replay_guard=guard,
        )
    assert exc.value.stage is CpsVerifyStage.GAMMA_REPLAY


def test_p0_cm_w_catalog_mismatch(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """P0: bundle.cm_w must match the catalog handle stored at registration."""
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            bundle,
            traces,
            catalog_cm_w_hex="00" * 32,
            session_id="toy-cm",
        )
    assert exc.value.stage is CpsVerifyStage.CM_W_CATALOG


def test_p5_tampered_w_star_opening_fails_pedersen_digest(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """P5: a tampered W* opening flips the Pedersen digest."""
    tampered = PyToyCpsBundle(**{**bundle.__dict__})
    tampered.w_star_opening = list(bundle.w_star_opening)
    tampered.w_star_opening[3] = (tampered.w_star_opening[3] + 1) % (2**128)
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            tampered,
            traces,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-open",
        )
    # cm_W catalog still matches (bundle.cm_w.cm_hex unchanged), so the
    # opening tamper is caught by the Pedersen digest check next.
    assert exc.value.stage is CpsVerifyStage.PEDERSEN_DIGEST


def test_p5_gamma_tamper_alone_undetectable_in_python(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """P5 honesty boundary: the M1 RLC identity is γ-agnostic — flipping γ
    in the challenge while leaving the trace honest still passes Python
    verification. Detection of γ-tamper requires the per-layer SNARK
    transcript check (Rust-side ``verify_X_toy``), demonstrated by the
    server-crypto Z.6 suite. This test fixes that fact so future client
    changes don't silently claim coverage they don't have.
    """
    tampered = PyToyCpsBundle(**{**bundle.__dict__})
    tampered.challenge = ClientChallenge(
        gamma="ff" * 32,
        gamma_add=bundle.challenge.gamma_add,
        gamma_mult=bundle.challenge.gamma_mult,
        num_pt_add=bundle.challenge.num_pt_add,
        num_pt_mult=bundle.challenge.num_pt_mult,
    )
    report = verify_toy_cps_bundle(
        tampered,
        traces,
        catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
        session_id="toy-gamma-python-only",
    )
    assert report.ok
    assert report.scalar_ok
    assert report.proof_coverage.startswith("cps_spartan_pc_plus_layer_pi_with_l1")


def test_p5_trace_outputs_mismatch_fails_scalar(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """Honest γ + tampered trace.outputs → M1 RLC identity breaks (scalar stage)."""
    bad_traces = PyToyCpsTraces(
        conv=type(traces.conv)(
            filter=list(traces.conv.filter),
            windows=[list(row) for row in traces.conv.windows],
            outputs=[999, *traces.conv.outputs[1:]],
        ),
        pool=traces.pool,
        fc=traces.fc,
    )
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            bundle,
            bad_traces,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-trace",
        )
    # L1 binding checks fc weights/bias and conv filter against W*; the
    # conv.outputs aren't in the L1 layout so we land on the SCALAR stage.
    assert exc.value.stage is CpsVerifyStage.SCALAR


def test_p3_l1_binding_rejects_trace_tamper(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """P3: trace.fc.weights diverging from W*[9..11] flips L1 binding."""
    bad = PyToyCpsTraces(
        conv=traces.conv,
        pool=traces.pool,
        fc=type(traces.fc)(
            input=traces.fc.input,
            weights=[99, traces.fc.weights[1]],
            bias=list(traces.fc.bias),
            outputs=list(traces.fc.outputs),
        ),
    )
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            bundle,
            bad,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-l1",
        )
    assert exc.value.stage is CpsVerifyStage.L1_BINDING


def test_schema_rejects_wrong_kind(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    """Bundle.cm_w.kind != spartan_pc → SCHEMA stage rejection."""
    tampered = PyToyCpsBundle(**{**bundle.__dict__})
    tampered.cm_w = type(bundle.cm_w)(
        cm_hex=bundle.cm_w.cm_hex,
        num_scalars=bundle.cm_w.num_scalars,
        padded_len=bundle.cm_w.padded_len,
        poly_comm_hex=list(bundle.cm_w.poly_comm_hex),
        kind="pedersen_legacy",
    )
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            tampered,
            traces,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-schema",
        )
    assert exc.value.stage is CpsVerifyStage.SCHEMA


def test_schema_rejects_opening_length_mismatch(
    bundle: PyToyCpsBundle, traces: PyToyCpsTraces
) -> None:
    tampered = PyToyCpsBundle(**{**bundle.__dict__})
    tampered.w_star_opening = list(bundle.w_star_opening) + [42]
    with pytest.raises(CpsVerifyError) as exc:
        verify_toy_cps_bundle(
            tampered,
            traces,
            catalog_cm_w_hex=TOY_W_STAR_CM_HEX,
            session_id="toy-schema2",
        )
    assert exc.value.stage is CpsVerifyStage.SCHEMA
