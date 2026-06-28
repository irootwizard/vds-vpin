"""AHE batch concurrency sweep — timing + memory stress test."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from vpin_client.bench.memory import CpuSampler, MemorySampler, process_rss_bytes, rss_mb_for_pids
from vpin_client.pipeline import BatchRequest, jobs_from_range, run_ahe_batch

EngineMode = Literal["python", "rust-ec", "rust-ark"]


@dataclass
class SweepRow:
    concurrency: int
    limit: int
    elapsed_s: float
    avg_s_per_image: float
    img_per_s: float
    accuracy: float
    correct: int
    rss_mb_start: float
    rss_mb_peak: float
    rss_mb_end: float
    watched_rss_peak_mb: float
    cpu_peak_pct: float
    warmup: bool
    error: str | None = None


@dataclass
class StressReport:
    engine: str
    backend: str
    model_id: str
    start: int
    limit: int
    concurrency_levels: list[int]
    watch_names: list[str]
    host: dict[str, Any]
    rows: list[SweepRow] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def best_throughput_row(self) -> SweepRow | None:
        ok = [r for r in self.rows if r.error is None]
        if not ok:
            return None
        return max(ok, key=lambda r: r.img_per_s)


def stress_report_to_dict(report: StressReport) -> dict[str, Any]:
    return asdict(report)


def _host_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "pid": os.getpid(),
    }


def _repo_root() -> Path:
    if env := os.environ.get("VPIN_REPO_ROOT"):
        return Path(env)
    return Path(__file__).resolve().parents[3]


def _client_root(repo: Path) -> Path:
    if env := os.environ.get("VPIN_CLIENT_ROOT"):
        return Path(env)
    if env := os.environ.get("VPIN_PLATFORM_ROOT"):
        return Path(env)
    return repo / "vpin-client"


def _ahe_cli_bin(client: Path) -> Path:
    win = client / "target" / "release" / "ahe-cli.exe"
    if win.is_file():
        return win
    alt = client / "target" / "release" / "ahe-cli"
    if alt.is_file():
        return alt
    # Pre-migration sibling vpin-platform (optional fallback)
    if client.parent is not None:
        legacy = client.parent / "vpin-platform" / "target" / "release" / "ahe-cli.exe"
        if legacy.is_file():
            return legacy
        legacy_unix = client.parent / "vpin-platform" / "target" / "release" / "ahe-cli"
        if legacy_unix.is_file():
            return legacy_unix
    return win


def _backend_root(repo: Path) -> Path:
    if env := os.environ.get("VPIN_BACKEND_ROOT"):
        return Path(env)
    return repo / "vpin-backend"


def _ahe_server_bin(backend: Path) -> Path:
    win = backend / "target" / "release" / "ahe-server.exe"
    if win.is_file():
        return win
    alt = backend / "target" / "release" / "ahe-server"
    if alt.is_file():
        return alt
    # Pre-migration sibling vpin-platform (optional fallback)
    if backend.parent is not None:
        legacy = backend.parent / "vpin-platform" / "target" / "release" / "ahe-server.exe"
        if legacy.is_file():
            return legacy
        legacy_unix = backend.parent / "vpin-platform" / "target" / "release" / "ahe-server"
        if legacy_unix.is_file():
            return legacy_unix
    return win


def _default_watch_names(engine: EngineMode) -> list[str]:
    if engine == "python":
        return ["python.exe", "python"]
    return ["ahe-cli.exe", "ahe-cli", "ahe-server.exe", "ahe-server"]


async def _run_python_batch_once(
    *,
    backend: str,
    model_id: str,
    start: int,
    limit: int,
    concurrency: int,
    watch_names: list[str],
) -> SweepRow:
    jobs = jobs_from_range(
        model_id=model_id, backend_ws=backend, start=start, limit=limit
    )
    request = BatchRequest(
        jobs=jobs,
        concurrency=concurrency,
        trace_mode="none",
        engine="python",
    )
    mem = MemorySampler(pids=[os.getpid()], watch_names=watch_names)
    cpu = CpuSampler()
    start_mb = mem.start()
    cpu.start()
    t0 = time.perf_counter()
    err: str | None = None
    report = None
    try:
        report = await run_ahe_batch(request, on_progress=None)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    elapsed = time.perf_counter() - t0
    end_mb = mem.stop()
    cpu_peak = cpu.stop()
    peak_mb = max(mem.peak_mb, start_mb, end_mb)
    watched_peak = max((mb for _, mb in mem.samples), default=0.0)

    if report is None:
        return SweepRow(
            concurrency=concurrency,
            limit=limit,
            elapsed_s=elapsed,
            avg_s_per_image=0.0,
            img_per_s=0.0,
            accuracy=0.0,
            correct=0,
            rss_mb_start=start_mb,
            rss_mb_peak=peak_mb,
            rss_mb_end=end_mb,
            watched_rss_peak_mb=watched_peak,
            cpu_peak_pct=cpu_peak,
            warmup=False,
            error=err or "batch failed",
        )

    avg = elapsed / limit if limit else 0.0
    return SweepRow(
        concurrency=concurrency,
        limit=limit,
        elapsed_s=elapsed,
        avg_s_per_image=avg,
        img_per_s=limit / elapsed if elapsed > 0 else 0.0,
        accuracy=report.accuracy,
        correct=report.correct,
        rss_mb_start=start_mb,
        rss_mb_peak=peak_mb,
        rss_mb_end=end_mb,
        watched_rss_peak_mb=watched_peak,
        cpu_peak_pct=cpu.peak_pct,
        warmup=False,
        error=err,
    )


def _run_rust_cli_once(
    *,
    engine: EngineMode,
    model_id: str,
    start: int,
    limit: int,
    concurrency: int,
    watch_names: list[str],
    on_tick: Any | None = None,
) -> SweepRow:
    repo = _repo_root()
    client_root = _client_root(repo)
    cli = _ahe_cli_bin(client_root)
    if not cli.is_file():
        return SweepRow(
            concurrency=concurrency,
            limit=limit,
            elapsed_s=0.0,
            avg_s_per_image=0.0,
            img_per_s=0.0,
            accuracy=0.0,
            correct=0,
            rss_mb_start=0.0,
            rss_mb_peak=0.0,
            rss_mb_end=0.0,
            watched_rss_peak_mb=0.0,
            cpu_peak_pct=0.0,
            warmup=False,
            error=f"ahe-cli not found: {cli}",
        )

    crypto = "ec" if engine == "rust-ec" else "ark"
    port = 8002 if engine == "rust-ec" else 8001
    cmd = [
        str(cli),
        "eval-mnist-ahe",
        "--model",
        model_id,
        "--start",
        str(start),
        "--limit",
        str(limit),
        "--concurrency",
        str(concurrency),
        "--progress",
        "--crypto-backend",
        crypto,
    ]
    env = os.environ.copy()
    env["VPIN_REPO_ROOT"] = str(repo)
    env["AHE_SERVER_PORT"] = str(port)
    bsgs = repo / "src" / "Pre_computed_table" / "table.bin"
    fixture = client_root / "tests" / "fixtures" / "table.bin"
    env["VPIN_BSGS_TABLE"] = str(fixture if fixture.is_file() else bsgs)

    mem = MemorySampler(pids=[os.getpid()], watch_names=watch_names)
    cpu = CpuSampler()
    start_mb = mem.start()
    cpu.start()
    t0 = time.perf_counter()
    err: str | None = None
    payload: dict[str, Any] | None = None
    last_tick = t0
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(client_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        mem.pids = [os.getpid(), proc.pid]

        def _drain_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                if line.strip() and on_tick:
                    on_tick(concurrency, line.strip())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        while proc.poll() is None:
            now = time.perf_counter()
            mb = mem.snapshot_mb()
            mem.peak_mb = max(mem.peak_mb, mb)
            mem.samples.append((now, mb))
            pct = cpu.snapshot_pct()
            cpu.peak_pct = max(cpu.peak_pct, pct)
            cpu.samples.append((now, pct))
            last_tick = now
            time.sleep(mem.interval_s)

        out, err_out = proc.communicate(timeout=30)
        stderr_thread.join(timeout=2.0)
        if proc.returncode != 0:
            err = (err_out or out or f"exit {proc.returncode}").strip()[:800]
        else:
            text = (out or "").strip()
            payload = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    elapsed = time.perf_counter() - t0
    end_mb = mem.stop()
    cpu.stop()
    peak_mb = max(mem.peak_mb, start_mb, end_mb)
    watched_peak = max((mb for _, mb in mem.samples), default=0.0)

    if payload is None:
        return SweepRow(
            concurrency=concurrency,
            limit=limit,
            elapsed_s=elapsed,
            avg_s_per_image=0.0,
            img_per_s=0.0,
            accuracy=0.0,
            correct=0,
            rss_mb_start=start_mb,
            rss_mb_peak=peak_mb,
            rss_mb_end=end_mb,
            watched_rss_peak_mb=watched_peak,
            cpu_peak_pct=cpu.peak_pct,
            warmup=False,
            error=err or "rust cli failed",
        )

    avg = elapsed / limit if limit else 0.0
    return SweepRow(
        concurrency=concurrency,
        limit=limit,
        elapsed_s=elapsed,
        avg_s_per_image=avg,
        img_per_s=limit / elapsed if elapsed > 0 else 0.0,
        accuracy=float(payload.get("accuracy", 0.0)),
        correct=int(payload.get("correct", 0)),
        rss_mb_start=start_mb,
        rss_mb_peak=peak_mb,
        rss_mb_end=end_mb,
        watched_rss_peak_mb=watched_peak,
        cpu_peak_pct=cpu.peak_pct,
        warmup=False,
        error=err,
    )


async def run_batch_stress(
    *,
    engine: EngineMode = "python",
    backend: str = "ws://127.0.0.1:8000/api/v1/session/ws",
    model_id: str = "cnn-mnist-trained",
    start: int = 0,
    limit: int = 64,
    concurrency_levels: list[int] | None = None,
    warmup: bool = True,
    watch_names: list[str] | None = None,
    on_row: Any | None = None,
    on_tick: Any | None = None,
) -> StressReport:
    """
    Sweep concurrency levels; measure wall time and RSS.

    `watch_names`: process executable names to include in RSS sum (best with psutil).
    `on_row`: optional callback(SweepRow) after each measurement.
    """
    levels = concurrency_levels or [1, 2, 4, 8, 16]
    levels = sorted({max(1, int(c)) for c in levels})
    names = watch_names if watch_names is not None else _default_watch_names(engine)

    report = StressReport(
        engine=engine,
        backend=backend,
        model_id=model_id,
        start=start,
        limit=limit,
        concurrency_levels=levels,
        watch_names=names,
        host=_host_info(),
    )
    incremental_path = write_stress_report(report)

    for level in levels:
        if warmup:
            if engine == "python":
                warm = await _run_python_batch_once(
                    backend=backend,
                    model_id=model_id,
                    start=start,
                    limit=min(4, limit),
                    concurrency=level,
                    watch_names=names,
                )
            else:
                warm = _run_rust_cli_once(
                    engine=engine,
                    model_id=model_id,
                    start=start,
                    limit=min(4, limit),
                    concurrency=level,
                    watch_names=names,
                    on_tick=on_tick,
                )
            warm.warmup = True
            if on_row:
                on_row(warm)

        if engine == "python":
            row = await _run_python_batch_once(
                backend=backend,
                model_id=model_id,
                start=start,
                limit=limit,
                concurrency=level,
                watch_names=names,
            )
        else:
            row = _run_rust_cli_once(
                engine=engine,
                model_id=model_id,
                start=start,
                limit=limit,
                concurrency=level,
                watch_names=names,
                on_tick=on_tick,
            )
        report.rows.append(row)
        if on_row:
            on_row(row)
        incremental_path.write_text(
            json.dumps(stress_report_to_dict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return report


def format_stress_table(report: StressReport) -> str:
    lines = [
        f"engine={report.engine} model={report.model_id} "
        f"start={report.start} limit={report.limit}",
        f"{'C':>4} {'time(s)':>8} {'s/img':>8} {'img/s':>8} "
        f"{'acc%':>6} {'cpu%':>6} {'rss_peak':>9} {'watch_peak':>11}  note",
        "-" * 80,
    ]
    for r in report.rows:
        tag = "warmup" if r.warmup else ""
        if r.error and not r.warmup:
            tag = f"ERR: {r.error[:40]}"
        lines.append(
            f"{r.concurrency:4d} {r.elapsed_s:8.1f} {r.avg_s_per_image:8.2f} "
            f"{r.img_per_s:8.2f} {100 * r.accuracy:6.1f} {r.cpu_peak_pct:6.0f} "
            f"{r.rss_mb_peak:8.0f}M {r.watched_rss_peak_mb:10.0f}M  {tag}"
        )
    best = report.best_throughput_row()
    if best:
        lines.append(
            f"\nbest img/s: concurrency={best.concurrency} "
            f"({best.img_per_s:.2f} img/s, cpu_peak={best.cpu_peak_pct:.0f}%, "
            f"rss_peak={best.rss_mb_peak:.0f}MB)"
        )
    best_cpu = max((r for r in report.rows if not r.warmup and not r.error), key=lambda r: r.cpu_peak_pct, default=None)
    if best_cpu and best_cpu is not best:
        lines.append(
            f"highest cpu: concurrency={best_cpu.concurrency} "
            f"(cpu_peak={best_cpu.cpu_peak_pct:.0f}%, img/s={best_cpu.img_per_s:.2f})"
        )
    return "\n".join(lines)


def write_stress_report(report: StressReport, out_dir: Path | None = None) -> Path:
    if out_dir is None:
        root = _repo_root()
        candidate = root / "reports"
        out_dir = candidate if root.is_dir() else Path.cwd() / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"bench_batch_{report.engine}_{report.limit}_{ts}.json"
    path.write_text(
        json.dumps(stress_report_to_dict(report), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def print_memory_hint() -> None:
    try:
        import psutil  # noqa: F401
    except ImportError:
        print(
            "tip: pip install psutil  →  watch-names RSS includes ahe-server/ahe-cli",
            file=sys.stderr,
        )


def current_process_rss_mb() -> float:
    b = process_rss_bytes(os.getpid())
    return (b or 0) / (1024 * 1024)


def sum_watch_rss_mb(names: list[str]) -> float:
    from vpin_client.bench.memory import pids_by_name

    return rss_mb_for_pids(pids_by_name(names))
