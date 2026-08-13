"""Export fused int64 weights for Network A compact AHE bundles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.network_a.model import NetworkA
from model_training.network_a.truncation_config import TruncationPlan
from model_training.network_a_compact.weight_fusion import export_compact_bundle


def export_compact_weights(
    run_dir: Path,
    *,
    out_dir: Path | None = None,
) -> Path:
    ckpt_path = run_dir / "checkpoint.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"missing checkpoint: {ckpt_path}")

    payload = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    plan_path = run_dir / "truncation_config.json"
    plan = TruncationPlan.load(plan_path) if plan_path.is_file() else TruncationPlan()
    model = NetworkA(plan=plan)
    model.load_state_dict(payload["state_dict"])

    w1 = model.fc1.weight.detach().numpy().T.astype(np.float64)
    b1 = model.fc1.bias.detach().numpy().astype(np.float64)
    w2 = model.fc2.weight.detach().numpy().T.astype(np.float64)
    b2 = model.fc2.bias.detach().numpy().astype(np.float64)

    bundle = export_compact_bundle(
        weight_fc1=w1,
        bias_fc1=b1,
        weight_fc2=w2,
        bias_fc2=b2,
    )

    dest = (out_dir or run_dir / "compact_weights").resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for name, arr in bundle.items():
        np.save(dest / name, arr)

    meta = {
        "variant": "network_a_compact",
        "source_run": str(run_dir.resolve()),
        "files": list(bundle.keys()),
        "client_rounds": 3,
        "skipped_phases": ["after_pool_shift", "after_fc1_shift"],
        "pool_strategy": "server sum//16 (plain) or pool_f26 + MAC>>10 (ciphertext)",
    }
    (dest / "compact_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Exported compact weights to {dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Network A compact fused weights")
    parser.add_argument("--run-dir", type=Path, required=True, help="Network A training output dir")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    export_compact_weights(args.run_dir.resolve(), out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
