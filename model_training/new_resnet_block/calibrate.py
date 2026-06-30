"""Calibrate block-linear approximations for new_resnet_block.

Loads a trained new_resnet checkpoint and fits a linear matrix A for each
target identity-shortcut block (or block pair) using calibration images
from the CIFAR-10 test set (no labels needed).

Linearization targets:
    layer1_both  — layer1[0] + layer1[1] merged   channel mode  A ∈ R^{64 × 64}
    layer2_b2    — layer2[1]                       channel mode  A ∈ R^{128 × 128}
    layer3_b2    — layer3[1]                       channel mode  A ∈ R^{256 × 256}
    layer4_b2    — layer4[1]                       full mode     A ∈ R^{8192 × 8192}

AHE meaning of A:
    The fitted A replaces the block in the AHE server pipeline:
        enc_y = A ⊗ enc_x   (homomorphic matmul at f=16 weights × f=16 input → f=32)
    The client then does shift(32→16) only (no relu), saving one client round per block.

Output (under model_training/new_resnet_block/block_linear_weights/):
    A_{target}.npy        — float32 weight matrix
    error_{target}.json   — calibration relative Frobenius error

Usage:
    python -m model_training.new_resnet_block.calibrate \\
        --checkpoint model_training/outputs/resnet18_<run_id>/checkpoint.pt

    # Calibrate only specific targets:
    python -m model_training.new_resnet_block.calibrate \\
        --checkpoint ... --targets layer1_both layer4_b2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_training.new_resnet.dataset import build_cifar10_loaders
from model_training.new_resnet_block.model import ResNet18, _LINEARIZE_TARGETS


# ---------------------------------------------------------------------------
# Linear fitting helpers
# ---------------------------------------------------------------------------

def _fit_channel(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit A ∈ R^{C × C} in channel mode via least squares.

    X, Y: float32 arrays of shape (N, C, H, W).
    Solves:  X_flat @ A.T ≈ Y_flat
    where X_flat, Y_flat ∈ R^{N·H·W × C}.

    Returns (A, rel_err):
        A        — float32 array of shape (C, C)
        rel_err  — relative Frobenius error ‖AX - Y‖_F / ‖Y‖_F on the calib set
    """
    N, C, H, W = X.shape
    # Each row = one (n, h, w) spatial sample's channel vector
    Xf = X.transpose(0, 2, 3, 1).reshape(-1, C).astype(np.float64)  # (N·H·W, C)
    Yf = Y.transpose(0, 2, 3, 1).reshape(-1, C).astype(np.float64)

    # lstsq(Xf, Yf) finds A.T ∈ R^{C×C} such that Xf @ A.T ≈ Yf
    A_T, _, _, _ = np.linalg.lstsq(Xf, Yf, rcond=None)
    A = A_T.T.astype(np.float32)

    Y_pred = (Xf @ A_T).astype(np.float64)
    err = float(np.linalg.norm(Y_pred - Yf, 'fro') / (np.linalg.norm(Yf, 'fro') + 1e-9))
    return A, err


def _fit_full(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit A ∈ R^{D × D} in full-spatial mode via least squares.

    X, Y: float32 arrays of shape (N, C, H, W).
    Solves:  X_flat @ A.T ≈ Y_flat  where X_flat, Y_flat ∈ R^{N × D}, D = C·H·W.

    Memory note: for layer4 B2 (D=8192, N=500):
        X_flat: 500×8192 ×8 bytes ≈ 32 MB
        A:      8192×8192 ×4 bytes ≈ 256 MB  (float32)
    The lstsq solution is minimum-norm (rank N, since N < D).
    """
    N, C, H, W = X.shape
    D = C * H * W
    Xf = X.reshape(N, D).astype(np.float64)
    Yf = Y.reshape(N, D).astype(np.float64)

    print(f"    lstsq: ({N}, {D}) → A: ({D}, {D})  [~{D*D*4/1e6:.0f} MB float32]")
    A_T, _, _, _ = np.linalg.lstsq(Xf, Yf, rcond=None)
    A = A_T.T.astype(np.float32)

    Y_pred = (Xf @ A_T).astype(np.float64)
    err = float(np.linalg.norm(Y_pred - Yf, 'fro') / (np.linalg.norm(Yf, 'fro') + 1e-9))
    return A, err


# ---------------------------------------------------------------------------
# Hook-based feature collection
# ---------------------------------------------------------------------------

def _collect_features(
    model: nn.Module,
    module: nn.Module,
    loader,
    num_calib: int,
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray]:
    """Run calibration images through model; capture input/output of module."""
    X_list: list[np.ndarray] = []
    Y_list: list[np.ndarray] = []

    def hook_pre(_mod, inp):
        X_list.append(inp[0].detach().cpu().float().numpy())

    def hook_post(_mod, _inp, out):
        Y_list.append(out.detach().cpu().float().numpy())

    h_pre  = module.register_forward_pre_hook(hook_pre)
    h_post = module.register_forward_hook(hook_post)

    n_collected = 0
    with torch.no_grad():
        for images, _ in loader:
            images = images.to(device)
            model(images)
            n_collected += images.size(0)
            if n_collected >= num_calib:
                break

    h_pre.remove()
    h_post.remove()

    X = np.concatenate(X_list, axis=0)[:num_calib]
    Y = np.concatenate(Y_list, axis=0)[:num_calib]
    return X, Y


# ---------------------------------------------------------------------------
# Main calibration routine
# ---------------------------------------------------------------------------

def calibrate(
    checkpoint: Path,
    num_calib: int = 500,
    batch_size: int = 64,
    targets: set[str] | None = None,
    output_dir: Path | None = None,
    device: str = "cuda",
) -> dict[str, dict]:
    """Fit and save linear approximations for all requested targets.

    Returns a summary dict: {target: {"rel_error": float, "A_shape": list}}.
    """
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    out_dir = (
        output_dir
        or REPO / "model_training" / "new_resnet_block" / "block_linear_weights"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    if targets is None:
        targets = set(_LINEARIZE_TARGETS.keys())

    print(f"Device  : {dev}")
    print(f"Targets : {sorted(targets)}")
    print(f"Calib N : {num_calib}")

    # Load the original ResNet18 weights from new_resnet checkpoint
    model = ResNet18()
    ckpt  = torch.load(checkpoint, map_location=dev, weights_only=False)
    state = ckpt.get("state_dict", ckpt)
    model.load_state_dict(state)
    model.to(dev).eval()
    print(f"Loaded  : {checkpoint}\n")

    # Re-use test loader as calibration source (no labels used)
    _, calib_loader = build_cifar10_loaders(batch_size=batch_size, num_workers=0)

    summary: dict[str, dict] = {}

    for target in sorted(targets):
        if target not in _LINEARIZE_TARGETS:
            print(f"[SKIP] Unknown target '{target}'")
            continue

        layer_attr, block_idx, C, H, W, mode = _LINEARIZE_TARGETS[target]
        layer  = getattr(model, layer_attr)
        module = layer if block_idx is None else layer[block_idx]

        print(f"[{target}] Collecting features …")
        X, Y = _collect_features(model, module, calib_loader, num_calib, dev)
        print(f"[{target}] X={X.shape}  Y={Y.shape}")

        print(f"[{target}] Fitting (mode={mode}) …")
        if mode == 'channel':
            A, err = _fit_channel(X, Y)
        else:
            A, err = _fit_full(X, Y)

        np.save(out_dir / f"A_{target}.npy", A)
        result = {
            "target":    target,
            "mode":      mode,
            "A_shape":   list(A.shape),
            "rel_error": err,
        }
        (out_dir / f"error_{target}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        summary[target] = result

        flag = "✓" if err < 0.10 else "⚠"
        print(f"[{target}] {flag} rel_err={err:.4f}  A saved → {out_dir}/A_{target}.npy\n")

    # ---------- Summary ----------
    print("=" * 50)
    print("Calibration summary")
    print("=" * 50)
    for t, r in sorted(summary.items()):
        flag = "✓" if r["rel_error"] < 0.10 else "⚠"
        ahe_rounds_saved = 3 if t == 'layer1_both' else 1
        print(
            f"  {flag} {t:15s}  mode={r['mode']:7s}  "
            f"err={r['rel_error']:.4f}  AHE rounds saved: {ahe_rounds_saved}"
        )
    print(f"\nWeights saved to: {out_dir}")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Calibrate block-linear weights for new_resnet_block",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--checkpoint",  type=Path, required=True,
                   help="Path to new_resnet checkpoint.pt")
    p.add_argument("--num-calib",   type=int,  default=500,
                   help="Number of calibration images (default 500)")
    p.add_argument("--batch-size",  type=int,  default=64)
    p.add_argument("--targets",     nargs="*", default=None,
                   metavar="TARGET",
                   help=(
                       "Blocks to calibrate. "
                       "Choices: layer1_both layer2_b2 layer3_b2 layer4_b2. "
                       "Default: all four."
                   ))
    p.add_argument("--output-dir",  type=Path, default=None,
                   help="Where to save A_*.npy files (default: block_linear_weights/)")
    p.add_argument("--device",      default="cuda")
    args = p.parse_args(argv)

    calibrate(
        checkpoint=args.checkpoint,
        num_calib=args.num_calib,
        batch_size=args.batch_size,
        targets=set(args.targets) if args.targets else None,
        output_dir=args.output_dir,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
