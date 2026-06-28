"""Cross-platform RSS sampling (optional psutil; Windows ctypes fallback)."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


def _rss_bytes_psutil(pid: int) -> int | None:
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return int(psutil.Process(pid).memory_info().rss)
    except Exception:
        return None


def _rss_bytes_windows(pid: int) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = kernel32.OpenProcess(0x1000 | 0x0400, False, pid)  # QUERY_LIMITED | VM_READ
        if not handle:
            return None
        try:
            ok = psapi.GetProcessMemoryInfo(
                handle,
                ctypes.byref(counters),
                counters.cb,
            )
            if not ok:
                return None
            return int(counters.WorkingSetSize)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def _rss_bytes_posix(pid: int) -> int | None:
    if sys.platform == "win32":
        return None
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except Exception:
        return None
    return None


def process_rss_bytes(pid: int) -> int | None:
    val = _rss_bytes_psutil(pid)
    if val is not None:
        return val
    val = _rss_bytes_windows(pid)
    if val is not None:
        return val
    return _rss_bytes_posix(pid)


def pids_by_name(names: list[str]) -> list[int]:
    """Return PIDs whose executable name matches any of `names` (needs psutil)."""
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return []
    wanted = {n.lower() for n in names}
    out: list[int] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname in wanted:
                out.append(int(proc.info["pid"]))
        except Exception:
            continue
    return out


def rss_mb_for_pids(pids: list[int]) -> float:
    total = 0
    for pid in pids:
        b = process_rss_bytes(pid)
        if b is not None:
            total += b
    return total / (1024 * 1024)


@dataclass
class CpuSampler:
    """Track system CPU utilization during a benchmark window."""

    interval_s: float = 0.5
    peak_pct: float = 0.0
    samples: list[tuple[float, float]] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def snapshot_pct(self) -> float:
        try:
            import psutil  # type: ignore[import-untyped]

            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return 0.0

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            pct = self.snapshot_pct()
            self.peak_pct = max(self.peak_pct, pct)
            self.samples.append((time.perf_counter(), pct))

    def start(self) -> float:
        try:
            import psutil  # type: ignore[import-untyped]

            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        pct0 = self.snapshot_pct()
        self.peak_pct = pct0
        self.samples = [(time.perf_counter(), pct0)]
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return pct0

    def stop(self) -> float:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        pct1 = self.snapshot_pct()
        self.peak_pct = max(self.peak_pct, pct1)
        return pct1


@dataclass
class MemorySampler:
    """Background RSS poller for one or more PIDs / process names."""

    pids: list[int] = field(default_factory=list)
    watch_names: list[str] = field(default_factory=list)
    interval_s: float = 0.5
    peak_mb: float = 0.0
    samples: list[tuple[float, float]] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def snapshot_mb(self) -> float:
        pids = list(self.pids)
        if self.watch_names:
            pids.extend(pids_by_name(self.watch_names))
        pids = list(dict.fromkeys(pids))
        return rss_mb_for_pids(pids)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            mb = self.snapshot_mb()
            self.peak_mb = max(self.peak_mb, mb)
            self.samples.append((time.perf_counter(), mb))

    def start(self) -> float:
        mb0 = self.snapshot_mb()
        self.peak_mb = mb0
        self.samples = [(time.perf_counter(), mb0)]
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return mb0

    def stop(self) -> float:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        mb1 = self.snapshot_mb()
        self.peak_mb = max(self.peak_mb, mb1)
        return mb1


def measure_call(
    fn: Callable[[], None],
    *,
    pids: list[int] | None = None,
    watch_names: list[str] | None = None,
    interval_s: float = 0.5,
) -> tuple[float, float, float]:
    """Run fn(); return (elapsed_s, rss_start_mb, rss_peak_mb)."""
    sampler = MemorySampler(
        pids=pids or [os.getpid()],
        watch_names=watch_names or [],
        interval_s=interval_s,
    )
    start_mb = sampler.start()
    t0 = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - t0
    end_mb = sampler.stop()
    peak_mb = max(sampler.peak_mb, start_mb, end_mb)
    return elapsed, start_mb, peak_mb
