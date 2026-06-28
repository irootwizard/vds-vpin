"""Export Network A FC weights to npy for AHE inference."""

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
sys.path.insert(0, str(REPO / "vpin-backend"))

from model_training.network_a.model import NetworkA
from model_training.network_a.truncation_config import TruncationPlan
from vpin_backend.models.weights_bundle import store_weights_path


def export_weights(run_dir: Path) -> None:
    ckpt_path = run_dir / "checkpoint.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"missing checkpoint: {ckpt_path}")

    payload = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    plan_path = run_dir / "truncation_config.json"
    if plan_path.is_file():
        plan = TruncationPlan.load(plan_path)
    elif isinstance(payload.get("plan"), dict):
        p = payload["plan"]
        plan = TruncationPlan(
            shift_pool=int(p.get("shift_pool", 26)),
            shift_fc1=int(p.get("shift_fc1", 32)),
        )
    else:
        plan = TruncationPlan()
    model = NetworkA(plan=plan)
    model.load_state_dict(payload["state_dict"])

    w1 = model.fc1.weight.detach().numpy().T.astype(np.float64)
    b1 = model.fc1.bias.detach().numpy().astype(np.float64)
    w2 = model.fc2.weight.detach().numpy().T.astype(np.float64)
    b2 = model.fc2.bias.detach().numpy().astype(np.float64)

    np.save(run_dir / "weight_fc1_64_16.npy", w1)
    np.save(run_dir / "bias_fc1_16.npy", b1)
    np.save(run_dir / "weight_fc2_16_10.npy", w2)
    np.save(run_dir / "bias_fc2_10.npy", b2)

    meta_path = run_dir / "metrics.json"
    meta = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["weights_exported"] = True
    meta["weights_dir"] = store_weights_path(run_dir, repo_root=REPO)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Exported weights to {run_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    export_weights(args.run_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
