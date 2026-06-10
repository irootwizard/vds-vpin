#!/usr/bin/env python3
"""
Write a minimal model_store bundle (record + manifest + model_export).
Usage (from repo root):
  python src/cp-snark-full/python/fill_model_store_sample.py --model-id vpin-network-a
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "model_store"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model-id", default="vpin-network-a")
    p.add_argument("--network", default="A")
    args = p.parse_args()

    model_dir = ROOT / "models" / args.model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "model_id": args.model_id,
        "display_name": f"vPIN Network {args.network} (generated)",
        "created_at_utc": now,
        "topology_network": args.network,
        "manifest_path": "manifest.json",
        "weights_path": "model_export.json",
        "source": {"kind": "vpin_npy", "version": 1},
        "commitment": {"status": "pending"},
        "truncation_plan": {"status": "stub", "plan_version": 0, "checkpoints": []},
    }
    manifest = {
        "model_id": args.model_id,
        "source": {"kind": "vpin_npy", "version": 1},
        "vpin_layout": {
            "version": 1,
            "network_folder": args.network,
            "conv_filter_inline": True,
        },
    }
    export = {
        "network_id": args.network,
        "conv_filter_flat": ["1", "0", "1", "2", "0", "2", "1", "0", "1"],
        "pool": {"kernel": 2, "stride": 2, "inv_k_squared_fp": "256"},
        "fc": [],
    }

    (model_dir / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (model_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (model_dir / "model_export.json").write_text(json.dumps(export, indent=2), encoding="utf-8")

    index_path = ROOT / "index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"version": 1, "models": []}
    rel = f"models/{args.model_id}/record.json"
    if not any(m.get("model_id") == args.model_id for m in index["models"]):
        index["models"].append({"model_id": args.model_id, "record_path": rel})
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"Wrote {model_dir}")


if __name__ == "__main__":
    main()
