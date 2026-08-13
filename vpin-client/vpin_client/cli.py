"""CLI entry for vpin-client."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from vpin_client.bench.batch_stress import (
    format_stress_table,
    print_memory_hint,
    run_batch_stress,
    stress_report_to_dict,
    write_stress_report,
)
from vpin_client.crypto.challenge import sample_challenge
from vpin_client.pipeline import (
    BatchRequest,
    InferenceJob,
    jobs_from_indices,
    jobs_from_json,
    jobs_from_range,
    run_ahe_batch,
    run_ahe_inference,
)
from vpin_client.pipeline.proof_pipeline import (
    fetch_proof_plan,
    is_network_a_proof_model,
    proof_result_to_dict,
    run_computation_proof,
    save_proof_artifact_remote,
    verify_proof_remote,
)


def _configure_stdio_utf8() -> None:
    """Piped stderr on Windows may default to GBK; trace 含中文时会 UnicodeEncodeError → exit 1."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _emit_progress_ndjson(phase: str, data: dict) -> None:
    payload = {"kind": "progress", "phase": phase, **data}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stderr.buffer.write(raw)
    sys.stderr.buffer.write(b"\n")
    sys.stderr.buffer.flush()


def _build_batch_jobs(args: argparse.Namespace) -> list[InferenceJob]:
    if args.jobs_json:
        raw = json.loads(Path(args.jobs_json).read_text(encoding="utf-8"))
        entries = raw if isinstance(raw, list) else raw.get("jobs", [])
        return jobs_from_json(entries, model_id=args.model, backend_ws=args.backend)

    if args.indices:
        indices = [int(x.strip()) for x in args.indices.split(",") if x.strip()]
        return jobs_from_indices(model_id=args.model, backend_ws=args.backend, indices=indices)

    return jobs_from_range(
        model_id=args.model,
        backend_ws=args.backend,
        start=args.start,
        limit=args.limit,
    )


async def _cmd_ahe_infer(args: argparse.Namespace) -> int:
    job = InferenceJob(
        model_id=args.model,
        backend_ws=args.backend,
        mnist_index=args.mnist_index,
        upload_id=args.upload_id,
        image_path=args.image,
        fixed_npy=args.fixed_npy,
    )

    def on_progress(phase: str, data: dict) -> None:
        if not args.progress_ndjson:
            return
        if phase == "trace":
            _emit_progress_ndjson("trace", {"step": data})
        else:
            _emit_progress_ndjson(phase, data)

    result = await run_ahe_inference(job, on_progress=on_progress if args.progress_ndjson else None)
    payload = result.to_dict()
    payload["infer_engine"] = args.infer_engine or "python"

    if args.timing or args.trace:
        if not args.trace and "trace" in payload:
            payload.pop("trace", None)
        print(json.dumps(payload, indent=2))
    else:
        print(f"prediction={result.prediction} label={result.label}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


async def _cmd_eval_mnist(args: argparse.Namespace) -> int:
    jobs = _build_batch_jobs(args)
    request = BatchRequest(
        jobs=jobs,
        concurrency=args.concurrency,
        trace_mode=args.trace_mode,
        engine=args.infer_engine or "python",
    )

    def on_progress(phase: str, data: dict) -> None:
        if args.progress_ndjson:
            if phase == "trace":
                _emit_progress_ndjson("trace", data)
            else:
                _emit_progress_ndjson(phase, data)
            return
        if phase != "batch_item" or not args.progress:
            return
        print(
            f"[ {data['index'] + 1:3d}/{data['limit']} ] correct={data['correct']} "
            f"acc={100.0 * data['accuracy']:.1f}% "
            f"elapsed={data['elapsed_s']:.1f}s eta={data['eta_s']:.1f}s",
            flush=True,
        )

    report = await run_ahe_batch(request, on_progress=on_progress)
    payload = report.to_dict()
    payload["infer_engine"] = request.engine
    print(json.dumps(payload, indent=2))

    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"batch_{report.limit}_{ts}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


async def _cmd_bench_mnist(args: argparse.Namespace) -> int:
    levels = [int(x.strip()) for x in args.concurrency.split(",") if x.strip()]
    watch = None
    if args.watch_names:
        watch = [x.strip() for x in args.watch_names.split(",") if x.strip()]
    print_memory_hint()

    def _print_row(row) -> None:
        if row.warmup:
            print(f"  warmup c={row.concurrency} {row.elapsed_s:.1f}s", flush=True)
            return
        print(
            f"  c={row.concurrency} elapsed={row.elapsed_s:.1f}s "
            f"avg={row.avg_s_per_image:.2f}s/img img/s={row.img_per_s:.2f} "
            f"cpu_peak={row.cpu_peak_pct:.0f}% "
            f"rss_peak={row.rss_mb_peak:.0f}MB watch={row.watched_rss_peak_mb:.0f}MB",
            flush=True,
        )

    def _print_tick(concurrency: int, line: str) -> None:
        if line.startswith("[") or "elapsed=" in line:
            print(f"    [c={concurrency}] {line}", flush=True)

    print(
        f"bench-mnist-ahe engine={args.engine} limit={args.limit} "
        f"levels={levels}",
        flush=True,
    )
    report = await run_batch_stress(
        engine=args.engine,
        backend=args.backend,
        model_id=args.model,
        start=args.start,
        limit=args.limit,
        concurrency_levels=levels,
        warmup=not args.no_warmup,
        watch_names=watch,
        on_row=_print_row,
        on_tick=_print_tick,
    )
    print(format_stress_table(report))
    out = Path(args.json_out) if args.json_out else write_stress_report(report)
    if args.json_out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stress_report_to_dict(report), indent=2), encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    failed = [r for r in report.rows if not r.warmup and r.error]
    return 1 if failed and len(failed) == len([r for r in report.rows if not r.warmup]) else 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdio_utf8()
    parser = argparse.ArgumentParser(prog="vpin-client", description="vPIN client tools")
    sub = parser.add_subparsers(dest="cmd")

    ch = sub.add_parser("sample-challenge", help="Sample P4 ClientChallenge (CSPRNG)")
    ch.add_argument("--num-pt-add", type=int, default=0)
    ch.add_argument("--num-pt-mult", type=int, default=0)

    infer = sub.add_parser("ahe-infer", help="Run pure AHE inference over WebSocket")
    infer.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    infer.add_argument("--model", default="cnn-mnist")
    infer.add_argument("--mnist-index", type=int, default=None)
    infer.add_argument("--upload-id", default=None)
    infer.add_argument("--image", default=None)
    infer.add_argument("--fixed-npy", default=None)
    infer.add_argument("--timing", action="store_true")
    infer.add_argument("--trace", action="store_true", help="Include per-phase inference trace in JSON output")
    infer.add_argument(
        "--progress-ndjson",
        action="store_true",
        help="Stream progress events as NDJSON lines on stderr (for Tauri UI timeline)",
    )
    infer.add_argument(
        "--infer-engine",
        default="python",
        help="Engine label echoed in result JSON (python | rust-ark | rust-ec)",
    )
    infer.add_argument("--json-out", default=None)

    ev = sub.add_parser("eval-mnist-ahe", help="Batch AHE evaluation")
    ev.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    ev.add_argument("--model", default="cnn-mnist-trained")
    ev.add_argument("--start", type=int, default=0)
    ev.add_argument("--limit", type=int, default=50)
    ev.add_argument("--indices", default=None, help="Comma-separated MNIST indices (overrides start/limit)")
    ev.add_argument("--jobs-json", default=None, help="JSON file with job list for mixed MNIST/upload batch")
    ev.add_argument("--progress", action="store_true", help="Human-readable progress on stderr")
    ev.add_argument(
        "--progress-ndjson",
        action="store_true",
        help="Stream batch progress as NDJSON on stderr (for Tauri UI)",
    )
    ev.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Parallel WS sessions (>1 enables P1+P2 batch pipeline; 1 = serial)",
    )
    ev.add_argument(
        "--trace-mode",
        choices=["none", "focus", "all"],
        default="none",
        help="Per-item inference trace streaming (all downgrades to focus when concurrency>1)",
    )
    ev.add_argument(
        "--infer-engine",
        default="python",
        help="Engine label in batch report (python | rust-ark | rust-ec)",
    )

    bench = sub.add_parser(
        "bench-mnist-ahe",
        help="Stress-test batch concurrency sweep (timing + memory)",
    )
    bench.add_argument(
        "--engine",
        choices=["python", "rust-ec", "rust-ark"],
        default="python",
        help="python=in-process vpin_client; rust-*=spawn ahe-cli",
    )
    bench.add_argument("--backend", default="ws://127.0.0.1:8000/api/v1/session/ws")
    bench.add_argument("--model", default="cnn-mnist-trained")
    bench.add_argument("--start", type=int, default=0)
    bench.add_argument("--limit", type=int, default=64)
    bench.add_argument(
        "--concurrency",
        default="1,2,4,8,16",
        help="Comma-separated concurrency levels to sweep",
    )
    bench.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup mini-batch before each measured run",
    )
    bench.add_argument(
        "--watch-names",
        default=None,
        help="Comma-separated process names for RSS sum (default by engine)",
    )
    bench.add_argument("--json-out", default=None, help="Write JSON report path")

    proof = sub.add_parser(
        "computation-proof",
        help="Network A computation proof P4–P6 (cp-snark-full via vpin-backend)",
    )
    proof.add_argument(
        "--backend-http",
        default="http://127.0.0.1:8000",
        help="vpin-backend HTTP root (not WebSocket)",
    )
    proof.add_argument("--model", default="cnn-mnist-trained")
    proof.add_argument("--network", default="A")
    proof.add_argument("--session-id", default="")
    proof.add_argument(
        "--skip-client-verify",
        action="store_true",
        help="Skip local M1 verify (server prove only)",
    )
    proof.add_argument(
        "--progress-ndjson",
        action="store_true",
        help="Emit proof phases on stderr as NDJSON",
    )

    proof_verify = sub.add_parser(
        "computation-proof-verify",
        help="P6 verify existing protocol.json on vpin-backend",
    )
    proof_verify.add_argument("--backend-http", default="http://127.0.0.1:8000")
    proof_verify.add_argument("--network", default="A")

    proof_save = sub.add_parser(
        "computation-proof-save",
        help="Save protocol.json to a local path",
    )
    proof_save.add_argument("--backend-http", default="http://127.0.0.1:8000")
    proof_save.add_argument("--network", default="A")
    proof_save.add_argument("--dest", required=True, help="Destination file path")
    proof_save.add_argument("--source", default="", help="Optional local source protocol.json")

    args = parser.parse_args(argv)
    if args.cmd == "sample-challenge":
        c = sample_challenge(args.num_pt_add, args.num_pt_mult)
        print(
            json.dumps(
                {
                    "gamma": c.gamma,
                    "gamma_add": c.gamma_add,
                    "gamma_mult": c.gamma_mult,
                    "num_pt_add": c.num_pt_add,
                    "num_pt_mult": c.num_pt_mult,
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "ahe-infer":
        try:
            return asyncio.run(_cmd_ahe_infer(args))
        except Exception as exc:
            if getattr(args, "progress_ndjson", False):
                _emit_progress_ndjson("error", {"message": str(exc)})
            try:
                print(f"ahe-infer failed: {exc}", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
            except Exception:
                sys.stderr.buffer.write(f"ahe-infer failed: {exc}\n".encode("utf-8", errors="replace"))
                sys.stderr.buffer.flush()
            return 1
    if args.cmd == "eval-mnist-ahe":
        try:
            return asyncio.run(_cmd_eval_mnist(args))
        except Exception as exc:
            if getattr(args, "progress_ndjson", False):
                _emit_progress_ndjson("error", {"message": str(exc)})
            print(f"eval-mnist-ahe failed: {exc}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            return 1
    if args.cmd == "bench-mnist-ahe":
        try:
            return asyncio.run(_cmd_bench_mnist(args))
        except Exception as exc:
            print(f"bench-mnist-ahe failed: {exc}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            return 1
    if args.cmd == "computation-proof":
        return _cmd_computation_proof(args)
    if args.cmd == "computation-proof-verify":
        return _cmd_computation_proof_verify(args)
    if args.cmd == "computation-proof-save":
        return _cmd_computation_proof_save(args)

    parser.print_help()
    return 1


async def _cmd_computation_proof_async(args: argparse.Namespace) -> int:
    if not is_network_a_proof_model(args.model):
        raise ValueError(f"computation-proof only supports Network A models, got {args.model!r}")
    backend = args.backend_http.rstrip("/")
    if args.progress_ndjson:
        _emit_progress_ndjson("proof_plan", {"model_id": args.model})
    plan = await fetch_proof_plan(f"{backend}/api/v1", model_id=args.model)
    if args.progress_ndjson:
        _emit_progress_ndjson(
            "proof_challenge",
            {"total_pt_mul": plan.total_pt_mul, "total_pt_add": plan.total_pt_add},
        )
    if args.progress_ndjson:
        _emit_progress_ndjson("proof_prove", {"message": "server cp-snark-full prove"})
    result = await run_computation_proof(
        f"{backend}/api/v1",
        model_id=args.model,
        network_id=args.network,
        session_id=args.session_id or "cli-proof",
        verify_locally=not args.skip_client_verify,
    )
    if args.progress_ndjson:
        _emit_progress_ndjson("proof_verify", {"verify_ok": result.verify_ok})
    raw: dict = {}
    if result.artifact_path and result.artifact_path.is_file():
        raw = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    payload = proof_result_to_dict(result, plan=plan, artifact_raw=raw)
    print(json.dumps(payload, indent=2))
    return 0 if result.ok and result.verify_ok else 1


def _cmd_computation_proof(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_cmd_computation_proof_async(args))
    except Exception as exc:
        if getattr(args, "progress_ndjson", False):
            _emit_progress_ndjson("error", {"message": str(exc)})
        print(f"computation-proof failed: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


async def _cmd_computation_proof_verify_async(args: argparse.Namespace) -> int:
    backend = args.backend_http.rstrip("/")
    result = await verify_proof_remote(f"{backend}/api/v1", network_id=args.network)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_computation_proof_verify(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_cmd_computation_proof_verify_async(args))
    except Exception as exc:
        print(f"computation-proof-verify failed: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


async def _cmd_computation_proof_save_async(args: argparse.Namespace) -> int:
    backend = args.backend_http.rstrip("/")
    source = Path(args.source) if args.source else None
    dest = Path(args.dest)
    await save_proof_artifact_remote(
        f"{backend}/api/v1",
        dest,
        network_id=args.network,
        source_path=source,
    )
    print(json.dumps({"ok": True, "dest": str(dest)}, indent=2))
    return 0


def _cmd_computation_proof_save(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_cmd_computation_proof_save_async(args))
    except Exception as exc:
        print(f"computation-proof-save failed: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
