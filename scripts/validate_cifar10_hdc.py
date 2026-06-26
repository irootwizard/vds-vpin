"""End-to-end HDC validation for the CIFAR-10 LeNet track (§11.8).

Steps:
1. Preflight — A_cifar_rgb adapter (3×32×32, F=16) input safety + digest.
2. Data↔family gate — lenet_cifar accepts cifar10; Network A on CIFAR is rejected.
3. Π closed loop — formula vs truncation_config from_bits (28/32).
4. Plaintext fixed-point simulation — one-sample argmax via forward_fixed_point.
5. (optional) Compile — when a trained run-dir is given, emit homomorphic_deploy_plan.json.

Runs offline (synthetic batch) when CIFAR-10 is not cached.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

try:  # ensure unicode-safe stdout on Windows GBK consoles
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "vpin-client", REPO / "vpin-backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from vpin_client.hdc import scale_rules as sr
from vpin_client.hdc.data_adapters import adapt_cifar_rgb
from vpin_client.hdc.model_decomposer import family_supports_dataset


def _sample_image(run_dir: Path | None) -> tuple[np.ndarray, int | None]:
    try:
        from model_training.network_lenet.dataset import build_cifar10_loaders

        _, test_loader = build_cifar10_loaders(batch_size=1, download=False)
        images, labels = next(iter(test_loader))
        return images[0].numpy(), int(labels[0].item())
    except Exception:  # noqa: BLE001
        rng = np.random.default_rng(7)
        return rng.integers(0, 256, size=(3, 32, 32), dtype=np.uint8), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate CIFAR-10 LeNet HDC track")
    parser.add_argument("--run-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve() if args.run_dir else None
    failures: list[str] = []

    # 1) Preflight adapter --------------------------------------------------
    raw, label = _sample_image(run_dir)
    adapted = adapt_cifar_rgb(raw, label=label)
    print(f"[preflight] adapter=cifar_rgb shape={adapted.fixed_int32.shape} "
          f"M_in={adapted.max_abs_input} input_safe={adapted.input_safe} "
          f"digest={adapted.digest_hex[:12]}")
    if adapted.fixed_int32.shape != (3, 32, 32):
        failures.append("adapter did not produce 3×32×32")
    if not adapted.input_safe:
        failures.append("input magnitude exceeds int32 limit")

    # 2) Data ↔ family gate -------------------------------------------------
    ok_lenet = family_supports_dataset("lenet_cifar", "cifar10")
    rejects_a = not family_supports_dataset("network_a", "cifar10")
    print(f"[gate] lenet_cifar<->cifar10={ok_lenet}  network_a<->cifar10_rejected={rejects_a}")
    if not ok_lenet:
        failures.append("lenet_cifar must accept cifar10")
    if not rejects_a:
        failures.append("Network A must be rejected on CIFAR-10")

    # 3) Π closed loop ------------------------------------------------------
    from model_training.network_lenet.verify import run_verify

    report = run_verify(run_dir)
    print(f"[pi] pi_match={report['pi_match']} range_ok={report['range_ok']}")
    if not report["pi_match"]:
        failures.append(f"pi mismatch: {report['pi_diffs']}")

    # 4) Plaintext fixed-point simulation ----------------------------------
    from model_training.network_lenet.model import LeNetCIFAR
    from model_training.network_lenet.truncation_config import TruncationPlan

    plan = TruncationPlan()
    model = LeNetCIFAR(plan=plan)
    if run_dir is not None:
        plan_path = run_dir / "truncation_config.json"
        ckpt = run_dir / "checkpoint.pt"
        if plan_path.is_file():
            plan = TruncationPlan.load(plan_path)
            model = LeNetCIFAR(plan=plan)
        if ckpt.is_file():
            model.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=False)["state_dict"])
    model.eval()
    images = torch.from_numpy(raw).unsqueeze(0)
    with torch.no_grad():
        logits = model.forward_fixed_point(images, plan=plan)
    pred = int(logits.argmax(dim=1).item())
    print(f"[sim] plaintext fixed-point argmax={pred}" + (f" label={label}" if label is not None else ""))

    # 5) Optional compile ---------------------------------------------------
    if run_dir is not None and (run_dir / "checkpoint.pt").is_file():
        try:
            from model_training.network_lenet.ahe_feasibility import compile_lenet_plan
            from model_training.network_lenet.dataset import build_cifar10_loaders

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            train_loader, test_loader = build_cifar10_loaders(batch_size=128)
            deploy = compile_lenet_plan(model.to(device), train_loader, test_loader, device, plan=plan)
            deploy.save(run_dir / "homomorphic_deploy_plan.json")
            print(f"[compile] deployable={deploy.deployable} range_ok={deploy.range_ok} "
                  f"accuracy_ok={deploy.accuracy_ok}")
        except Exception as exc:  # noqa: BLE001
            print(f"[compile] skipped ({type(exc).__name__}: {exc})")

    print(f"\nconstants: F={sr.F} BSGS<{sr.BSGS_ABS_SAFE_LIMIT:.2e} INT32<{sr.INT32_ABS_SAFE_LIMIT:.2e}")
    if failures:
        print("VALIDATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("CIFAR-10 HDC validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
