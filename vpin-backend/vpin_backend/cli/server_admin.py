"""
Server-side model registration (CLI), per Task3 server ingest path.

Example:
  python -m vpin_backend.cli.server_admin register --network A --name "CNN A"
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from vpin_backend.config import get_settings
from vpin_backend.crypto.cp_snark.bridge import CpSnarkBridge

NETWORK_TO_VERSION = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}


def _registry_path() -> Path:
    settings = get_settings()
    path = settings.resolved_data_dir / "models" / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> list[dict]:
    path = _registry_path()
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save(entries: list[dict]) -> None:
    path = _registry_path()
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def cmd_register(args: argparse.Namespace) -> None:
    settings = get_settings()
    network = args.network.upper()
    if network not in NETWORK_TO_VERSION:
        raise SystemExit(f"unknown network {network}, use A–E")

    src_dir = settings.cnn_networks_dir / "Pre_trained_model"
    dest = settings.resolved_data_dir / "models" / f"cnn-{network.lower()}"
    dest.mkdir(parents=True, exist_ok=True)
    for npy in src_dir.glob("*.npy"):
        shutil.copy2(npy, dest / npy.name)

    commitment_digest = None
    if args.commit:
        bridge = CpSnarkBridge()
        if not bridge.is_available():
            raise SystemExit("cp-snark-full not found; skip --commit or install Rust")
        r = bridge.run_phase(network, "setup")
        if not r.ok:
            raise SystemExit(f"setup failed: {r.stderr}")
        if r.summary:
            commitment_digest = r.summary.get("cm_w")

    model_id = args.id or f"cnn-{network.lower()}"
    entry = {
        "id": model_id,
        "name": args.name or f"CNN network {network}",
        "framework": "npy",
        "task": "图像分类",
        "params_count_m": 1.0,
        "input_shape": "1x28x28",
        "accuracy": 0.0,
        "network": network,
        "topology": "cnn_mnist_v1",
        "weight_dir": str(dest),
        "weights_dir": str(dest),
        "updated": datetime.now(timezone.utc).isoformat(),
        "commitment_digest": commitment_digest,
    }

    entries = [e for e in _load() if e.get("id") != model_id]
    entries.append(entry)
    _save(entries)
    print(f"registered {model_id} -> {dest}")
    if commitment_digest:
        print(f"cm_W digest prefix: {commitment_digest[:32]}...")


def cmd_list(_: argparse.Namespace) -> None:
    for e in _load():
        print(f"{e['id']}\t{e.get('name')}\tnetwork={e.get('network')}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="vpin-admin")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Register server-side npy model pack")
    reg.add_argument("--network", required=True, help="A–E (maps to rust_files folder)")
    reg.add_argument("--name", default=None)
    reg.add_argument("--id", default=None)
    reg.add_argument("--commit", action="store_true", help="Run CP-SNARK setup for cm_W")
    reg.set_defaults(func=cmd_register)

    lst = sub.add_parser("list", help="List registered models")
    lst.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
