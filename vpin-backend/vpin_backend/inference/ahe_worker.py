"""ResNet server-side homomorphic step worker via Rust subprocess.

Spawns a long-running ``ahe-resnet-worker`` binary that holds the engine state
between phases, avoiding the startup cost of loading 37 weight files per step.

Ciphertexts cross the process boundary as ``(x, y)`` decimal-integer pairs
matching the Python ``ecdsa.Point`` coordinates.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import numpy as np
from ecdsa.ellipticcurve import Point

from vpin_backend.crypto.ahe.curve import curve_e2_info

_WORKER_BIN = "ahe-resnet-worker"


def _find_worker_binary() -> str:
    from vpin_backend.config import get_settings

    repo_root = get_settings().repo_root
    candidates = [
        repo_root / "vpin-client" / "target" / "release" / _WORKER_BIN,
        repo_root / "vpin-client" / "target" / "release" / f"{_WORKER_BIN}.exe",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    # fall back to PATH
    return _WORKER_BIN


def _xy_flat(arr: np.ndarray) -> list[tuple[str, str] | None]:
    flat = arr.reshape(-1)
    out: list[tuple[str, str] | None] = []
    for p in flat:
        if isinstance(p, Point):
            x, y = p.x(), p.y()
            if x is not None and y is not None:
                out.append((str(int(x)), str(int(y))))
            else:
                out.append(None)
        else:
            out.append(None)
    return out


def _pack_to_array(pack: tuple[tuple[int, ...], list[tuple[int, int] | None]]) -> np.ndarray:
    shape, flat = pack
    curve, _, _, _, _ = curve_e2_info()
    arr = np.empty(len(flat), dtype=object)
    for i, xy in enumerate(flat):
        if xy is None:
            arr[i] = Point(curve, 0, 0)  # identity placeholder
        else:
            arr[i] = Point(curve, int(xy[0]), int(xy[1]))
    return arr.reshape(shape)


def points_to_xy(arr: np.ndarray) -> tuple[tuple[int, ...], list[tuple[int, int] | None]]:
    flat = arr.reshape(-1)
    out: list[tuple[int, int] | None] = []
    for p in flat:
        if isinstance(p, Point):
            x, y = p.x(), p.y()
            if x is not None and y is not None:
                out.append((int(x), int(y)))
            else:
                out.append(None)  # identity / point-at-infinity
        else:
            out.append(None)
    return arr.shape, out


class ResNetRustWorker:
    """Manages a long-running `ahe-resnet-worker` subprocess."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._initialized = False
        self._weights_dir: str | None = None
        self._pubkey_xy: tuple[int, int] | None = None

    def _ensure_started(self, weights_dir: str, pubkey_xy: tuple[int, int]) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is not None:
                self._proc = None
                self._initialized = False

            if self._proc is None:
                bin_path = _find_worker_binary()
                self._proc = subprocess.Popen(
                    [bin_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    bufsize=1,
                )
                self._stderr_lines: list[str] = []
                self._stderr_thread = threading.Thread(
                    target=self._read_stderr, daemon=True
                )
                self._stderr_thread.start()

            if not self._initialized or (
                self._weights_dir != weights_dir or self._pubkey_xy != pubkey_xy
            ):
                self._send_cmd_locked(
                    {
                        "cmd": "init",
                        "weights_dir": weights_dir,
                        "pubkey_x": str(pubkey_xy[0]),
                        "pubkey_y": str(pubkey_xy[1]),
                    }
                )
                self._weights_dir = weights_dir
                self._pubkey_xy = pubkey_xy
                self._initialized = True

    def _read_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        try:
            for line in self._proc.stderr:
                self._stderr_lines.append(line)
        except Exception:
            pass

    def _send_cmd_locked(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON command and read the response.  Caller must hold self._lock."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        line = json.dumps(cmd, ensure_ascii=False)
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()
        resp_line = self._proc.stdout.readline()
        if not resp_line:
            # drain stderr thread
            self._stderr_thread.join(timeout=2)
            stderr = "".join(self._stderr_lines[-20:])
            rc = self._proc.poll()
            import sys
            sys.stderr.write(f"[worker CRASH] rc={rc} stderr:\n{stderr}\n")
            sys.stderr.flush()
            raise RuntimeError(
                f"ahe-resnet-worker exited prematurely (rc={rc})\nstderr:\n{stderr}"
            )
        return json.loads(resp_line)

    def _send_cmd(self, cmd: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._send_cmd_locked(cmd)

    def step(
        self,
        phase_id: str,
        c1_pack: tuple[tuple[int, ...], list[tuple[int, int] | None]],
        c2_pack: tuple[tuple[int, ...], list[tuple[int, int] | None]],
    ) -> dict[str, Any]:
        shape, c1_flat = c1_pack
        c1_xy = [None if xy is None else (str(xy[0]), str(xy[1])) for xy in c1_flat]
        c2_xy = [
            None if xy is None else (str(xy[0]), str(xy[1])) for xy in c2_pack[1]
        ]

        resp = self._send_cmd(
            {
                "cmd": "step",
                "phase_id": phase_id,
                "c1_xy": c1_xy,
                "c2_xy": c2_xy,
                "shape": list(shape),
            }
        )
        if not resp.get("ok"):
            raise RuntimeError(f"worker step error: {resp.get('error', 'unknown')}")
        return resp

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.stdout.close()
            except Exception:
                pass
            try:
                self._proc.stderr.close()
            except Exception:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
            self._initialized = False


class ResNetWorkerSession:
    """Per-session context that bridges Python session.py ↔ Rust worker.

    Usage in session.py::

        rw = ResNetWorkerSession.ensure(weights_dir, pubkey_xy)
        # ... per phase:
        res = rw.step(phase_id, points_to_xy(c1), points_to_xy(c2))
        out_c1 = _pack_to_array(res["out_c1"])
        # ...
        rw.release()  # when session ends
    """

    _worker: ResNetRustWorker | None = None
    _refcount: int = 0
    _lock = threading.Lock()

    def __init__(
        self, worker: ResNetRustWorker, weights_dir: str, pubkey_xy: tuple[int, int]
    ) -> None:
        self._w = worker
        self._weights_dir = weights_dir
        self._pubkey_xy = pubkey_xy
        self._add = 0
        self._mult = 0

    @classmethod
    def ensure(cls, weights_dir: str, pubkey_xy: tuple[int, int]) -> ResNetWorkerSession:
        with cls._lock:
            if cls._worker is None:
                cls._worker = ResNetRustWorker()
            cls._refcount += 1
            cls._worker._ensure_started(weights_dir, pubkey_xy)
        return cls(worker=cls._worker, weights_dir=weights_dir, pubkey_xy=pubkey_xy)

    def step(
        self,
        phase_id: str,
        c1_pack: tuple[tuple[int, ...], list[tuple[int, int] | None]],
        c2_pack: tuple[tuple[int, ...], list[tuple[int, int] | None]],
    ) -> dict[str, Any]:
        resp = self._w.step(phase_id, c1_pack, c2_pack)
        self._add += resp.get("add", 0)
        self._mult += resp.get("mult", 0)
        return resp

    @property
    def total_add(self) -> int:
        return self._add

    @property
    def total_mult(self) -> int:
        return self._mult

    def release(self) -> None:
        with type(self)._lock:
            type(self)._refcount = max(0, type(self)._refcount - 1)
            if type(self)._refcount == 0 and type(self)._worker is not None:
                type(self)._worker.close()
                type(self)._worker = None
