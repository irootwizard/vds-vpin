"""Pull large runtime artifacts (BSGS tables) on first init; verify SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ProgressCb = Callable[[dict[str, Any]], None]

_MANIFEST_NAME = "runtime-artifacts.manifest.json"


def detect_repo_root() -> Path:
    env = os.environ.get("VPIN_REPO_ROOT")
    if env:
        p = Path(env)
        if p.is_dir():
            return p.resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "vpin-client").is_dir() and (parent / "model_training").is_dir():
            return parent
    return Path.cwd().resolve()


def manifest_path(repo: Path | None = None) -> Path:
    root = repo or detect_repo_root()
    return root / "config" / _MANIFEST_NAME


def load_manifest(repo: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo)
    if not path.is_file():
        raise FileNotFoundError(f"missing artifact manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def artifacts_base_url(manifest: dict[str, Any]) -> str | None:
    env_key = str(manifest.get("base_url_env", "VPIN_ARTIFACTS_BASE_URL"))
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return None
    return raw.rstrip("/") + "/"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _artifact_ok(path: Path, expected_sha: str | None, expected_size: int | None) -> bool:
    if not path.is_file():
        return False
    if expected_size and path.stat().st_size != expected_size:
        return False
    if expected_sha and _sha256_file(path).lower() != expected_sha.lower():
        return False
    return True


def _emit(cb: ProgressCb | None, payload: dict[str, Any]) -> None:
    if cb:
        cb(payload)
    else:
        kind = payload.get("event", "info")
        msg = payload.get("message", "")
        if kind == "error":
            print(msg, file=sys.stderr)
        elif kind != "progress":
            print(msg)


def _download_file(
    url: str,
    dest: Path,
    *,
    expected_sha: str | None,
    expected_size: int | None,
    progress: ProgressCb | None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "vpin-client-bootstrap/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or expected_size or 0)
            done = 0
            with tmp.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        _emit(
                            progress,
                            {
                                "event": "progress",
                                "url": url,
                                "dest": str(dest),
                                "bytes_done": done,
                                "bytes_total": total,
                                "percent": round(100.0 * done / total, 1),
                            },
                        )
    except urllib.error.URLError as exc:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download failed {url}: {exc}") from exc

    if expected_size and tmp.stat().st_size != expected_size:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"size mismatch for {dest.name}: expected {expected_size}")

    if expected_sha:
        got = _sha256_file(tmp).lower()
        if got != expected_sha.lower():
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"sha256 mismatch for {dest.name}")

    tmp.replace(dest)


def pull_runtime_artifacts(
    *,
    repo: Path | None = None,
    ids: list[str] | None = None,
    only_rust: bool = False,
    only_python: bool = False,
    force: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Download missing remote artifacts listed in the manifest."""
    root = repo or detect_repo_root()
    manifest = load_manifest(root)
    base = artifacts_base_url(manifest)
    if not base:
        return {
            "ok": True,
            "skipped": True,
            "reason": "VPIN_ARTIFACTS_BASE_URL not set",
            "pulled": [],
            "already_present": [],
        }

    pulled: list[str] = []
    already: list[str] = []
    errors: list[str] = []

    for entry in manifest.get("remote", []):
        art_id = str(entry["id"])
        if ids and art_id not in ids:
            continue
        req_for = entry.get("required_for") or []
        if only_rust and "rust_ahe" not in req_for:
            continue
        if only_python and "python_ahe" not in req_for:
            continue

        rel_dest = Path(str(entry["dest"]))
        dest = root / rel_dest if not rel_dest.is_absolute() else rel_dest
        sha = entry.get("sha256")
        size = entry.get("size_bytes")
        if not force and _artifact_ok(dest, sha, size):
            already.append(art_id)
            _emit(progress, {"event": "info", "message": f"[skip] {art_id} already at {dest}"})
            continue

        url_path = str(entry.get("url_path", dest.name))
        url = base + url_path.lstrip("/")
        _emit(progress, {"event": "info", "message": f"[pull] {art_id} ← {url}"})
        try:
            _download_file(url, dest, expected_sha=sha, expected_size=size, progress=progress)
            pulled.append(art_id)
            _emit(progress, {"event": "info", "message": f"[done] {art_id} → {dest}"})
        except Exception as exc:
            errors.append(f"{art_id}: {exc}")
            _emit(progress, {"event": "error", "message": str(exc)})

    ok = not errors
    return {
        "ok": ok,
        "skipped": False,
        "base_url": base,
        "pulled": pulled,
        "already_present": already,
        "errors": errors,
    }


def ensure_runtime_artifacts(
    *,
    repo: Path | None = None,
    rust: bool = True,
    python: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Ensure artifacts needed at startup; pull only when base URL is configured."""
    root = repo or detect_repo_root()
    manifest = load_manifest(root)
    status: dict[str, Any] = {"repo_root": str(root), "bundled_ok": True, "remote": None}

    for bundle in manifest.get("bundled", []):
        dest = root / str(bundle["dest"])
        missing = [name for name in bundle.get("files", []) if not (dest / name).is_file()]
        if missing:
            status["bundled_ok"] = False
            status.setdefault("bundled_missing", []).append(
                {"id": bundle.get("id"), "dest": str(dest), "files": missing}
            )

    if rust or python:
        status["remote"] = pull_runtime_artifacts(
            repo=root,
            only_rust=rust and not python,
            only_python=python and not rust,
            progress=progress,
        )
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pull vPIN runtime artifacts (BSGS tables, etc.)")
    parser.add_argument("--repo", type=Path, default=None, help="vPIN repo root")
    parser.add_argument("--id", action="append", dest="ids", help="artifact id (repeatable)")
    parser.add_argument("--rust-only", action="store_true", help="only Rust table.bin")
    parser.add_argument("--python-only", action="store_true", help="only Python table.pickle")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--ensure", action="store_true", help="ensure startup artifacts (default)")
    parser.add_argument("--json", action="store_true", help="print JSON result")
    args = parser.parse_args(argv)

    repo = args.repo.resolve() if args.repo else detect_repo_root()

    if args.ensure and not args.ids and not args.force:
        result = ensure_runtime_artifacts(
            repo=repo,
            rust=not args.python_only,
            python=args.python_only,
            progress=None,
        )
    else:
        result = pull_runtime_artifacts(
            repo=repo,
            ids=args.ids,
            only_rust=args.rust_only,
            only_python=args.python_only,
            force=args.force,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("errors"):
        for err in result["errors"]:
            print(err, file=sys.stderr)

    if result.get("skipped"):
        return 0
    remote = result.get("remote") if isinstance(result.get("remote"), dict) else None
    if remote and remote.get("skipped"):
        bundled_ok = result.get("bundled_ok", True) if "bundled_ok" in result else True
        return 0 if bundled_ok else 1
    return 0 if result.get("ok", True) and result.get("bundled_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
