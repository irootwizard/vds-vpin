"""Export LeNet-CIFAR conv + FC weights to npy for HDC compile / AHE inference."""

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

from model_training.network_lenet.model import LeNetCIFAR
from model_training.network_lenet.truncation_config import TruncationPlan
from vpin_backend.models.weights_bundle import store_weights_path

# npy file naming: conv weights as (out,in,kh,kw); fc weights transposed to (in,out)
# to match the homomorphic FC matmul convention (x @ W).
EXPORT_FILES = (
    "weight_conv1_6_3_5_5.npy",
    "bias_conv1_6.npy",
    "weight_conv2_16_6_5_5.npy",
    "bias_conv2_16.npy",
    "weight_fc1_400_120.npy",
    "bias_fc1_120.npy",
    "weight_fc2_120_84.npy",
    "bias_fc2_84.npy",
    "weight_fc3_84_10.npy",
    "bias_fc3_10.npy",
)


def export_weights(run_dir: Path) -> None:
    ckpt_path = run_dir / "checkpoint.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"missing checkpoint: {ckpt_path}")
    payload = torch.load(ckpt_path, map_location="cpu", weights_only=False)

    plan_path = run_dir / "truncation_config.json"
    plan = TruncationPlan.load(plan_path) if plan_path.is_file() else TruncationPlan()
    model = LeNetCIFAR(plan=plan)
    model.load_state_dict(payload["state_dict"])

    def npy(t: torch.Tensor) -> np.ndarray:
        return t.detach().cpu().numpy().astype(np.float64)

    np.save(run_dir / "weight_conv1_6_3_5_5.npy", npy(model.conv1.weight))
    np.save(run_dir / "bias_conv1_6.npy", npy(model.conv1.bias))
    np.save(run_dir / "weight_conv2_16_6_5_5.npy", npy(model.conv2.weight))
    np.save(run_dir / "bias_conv2_16.npy", npy(model.conv2.bias))
    np.save(run_dir / "weight_fc1_400_120.npy", npy(model.fc1.weight).T)
    np.save(run_dir / "bias_fc1_120.npy", npy(model.fc1.bias))
    np.save(run_dir / "weight_fc2_120_84.npy", npy(model.fc2.weight).T)
    np.save(run_dir / "bias_fc2_84.npy", npy(model.fc2.bias))
    np.save(run_dir / "weight_fc3_84_10.npy", npy(model.fc3.weight).T)
    np.save(run_dir / "bias_fc3_10.npy", npy(model.fc3.bias))

    if not plan_path.is_file():
        plan.save(plan_path)

    meta_path = run_dir / "metrics.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    meta["weights_exported"] = True
    meta["weights_dir"] = store_weights_path(run_dir, repo_root=REPO)
    meta["export_files"] = list(EXPORT_FILES)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Exported LeNet-CIFAR weights to {run_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    export_weights(args.run_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
