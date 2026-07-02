"""Truncation plan and BSGS/INT32 safety estimates for new_resnet (ResNet18/CIFAR-10) AHE pipeline.

ResNet18 AHE flow (17 relu_then_shift rounds + 1 argmax):
  All Conv+BN pairs are BN-folded offline before deployment.
  Residual connections:
    - Identity shortcut (layer1 both blocks, layer2/3/4 block1):
        shortcut (f=16) × 2^16  → align to f=32, server adds to conv2 output (f=32)
    - Downsample shortcut (layer2/3/4 block0):
        server runs ds_conv(1×1)+BN_fold on block input (f=16) → f=32,
        holds it, then adds to conv2 output (f=32). Both already at f=32.

BSGS_LIMIT ≈ 2^43 (~8.8×10^12); INT32_LIMIT = 2^31−1
"""

from __future__ import annotations

FIXED_POINT_BITS = 16
WEIGHT_BITS      = 16
POST_LAYER_BITS  = FIXED_POINT_BITS + WEIGHT_BITS  # 32

BSGS_LIMIT  = 2**43
INT32_LIMIT = 2**31 - 1

# ---------------------------------------------------------------------------
# Truncation plan — 17 relu_then_shift phases + 1 logits_only
# ---------------------------------------------------------------------------
TRUNCATION_PLAN = [
    # ── Stem ──────────────────────────────────────────────────────────────
    {
        "phase_id":      "after_stem",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 64, 32, 32],   # conv1(3→64,3×3,p=1)+BN_fold output
        "output_shape":  [1, 64, 32, 32],
        "shortcut":      None,
    },
    # ── Layer1 Block0 (identity shortcut) ─────────────────────────────────
    {
        "phase_id":      "after_l1b0c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 64, 32, 32],
        "output_shape":  [1, 64, 32, 32],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l1b0c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 64, 32, 32],
        "output_shape":  [1, 64, 32, 32],
        "shortcut":      "identity",          # server: shortcut × 2^16 + conv2_out
    },
    # ── Layer1 Block1 (identity shortcut) ─────────────────────────────────
    {
        "phase_id":      "after_l1b1c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 64, 32, 32],
        "output_shape":  [1, 64, 32, 32],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l1b1c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 64, 32, 32],
        "output_shape":  [1, 64, 32, 32],
        "shortcut":      "identity",
    },
    # ── Layer2 Block0 (downsample shortcut, stride=2) ──────────────────────
    {
        "phase_id":      "after_l2b0c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 128, 16, 16],   # conv1(64→128,3×3,s=2)+BN_fold
        "output_shape":  [1, 128, 16, 16],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l2b0c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 128, 16, 16],
        "output_shape":  [1, 128, 16, 16],
        "shortcut":      "downsample",        # server holds ds_conv output (f=32)
    },
    # ── Layer2 Block1 (identity shortcut) ─────────────────────────────────
    {
        "phase_id":      "after_l2b1c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 128, 16, 16],
        "output_shape":  [1, 128, 16, 16],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l2b1c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 128, 16, 16],
        "output_shape":  [1, 128, 16, 16],
        "shortcut":      "identity",
    },
    # ── Layer3 Block0 (downsample shortcut, stride=2) ──────────────────────
    {
        "phase_id":      "after_l3b0c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 256, 8, 8],
        "output_shape":  [1, 256, 8, 8],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l3b0c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 256, 8, 8],
        "output_shape":  [1, 256, 8, 8],
        "shortcut":      "downsample",
    },
    # ── Layer3 Block1 (identity shortcut) ─────────────────────────────────
    {
        "phase_id":      "after_l3b1c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 256, 8, 8],
        "output_shape":  [1, 256, 8, 8],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l3b1c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 256, 8, 8],
        "output_shape":  [1, 256, 8, 8],
        "shortcut":      "identity",
    },
    # ── Layer4 Block0 (downsample shortcut, stride=2) ──────────────────────
    {
        "phase_id":      "after_l4b0c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 512, 4, 4],
        "output_shape":  [1, 512, 4, 4],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l4b0c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 512, 4, 4],
        "output_shape":  [1, 512, 4, 4],
        "shortcut":      "downsample",
    },
    # ── Layer4 Block1 (identity shortcut) ─────────────────────────────────
    {
        "phase_id":      "after_l4b1c1",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 512, 4, 4],
        "output_shape":  [1, 512, 4, 4],
        "shortcut":      None,
    },
    {
        "phase_id":      "after_l4b1c2",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 512, 4, 4],
        "output_shape":  [1, 512, 4, 4],
        "shortcut":      "identity",
    },
    # ── Final: AvgPool(4×4) + Linear(512→10) merged, then argmax ──────────
    # Server combines pool+linear in one step (both linear, no intermediate
    # re-encrypt needed). Output f = 16 (pool input) + 16 (weight) + log2(16) (pool sum) = 36
    # ⚠须校准验证: |logits| < BSGS_LIMIT before argmax
    {
        "phase_id":      "after_pool_linear",
        "client_action": "logits_only",
        "shift_bits":    None,
        "input_shape":   [1, 10],
        "output_shape":  None,
        "shortcut":      None,
    },
]


def check_bsgs_safety(*, verbose: bool = False) -> bool:
    """Worst-case estimate using conservative w_max = 0.1 * 2^WEIGHT_BITS.

    After BN folding, effective weights are typically in a small range.
    Use w_max_float = 0.1 (i.e. 6554 at f=16) as a conservative bound.
    If actual trained weights exceed this, a calibration run with real
    data is required to verify the constraint.
    """
    ok = True
    rows = []

    x_max   = 2**FIXED_POINT_BITS               # input pixel at f=16 ≈ 65536
    w_max   = int(0.1 * 2**WEIGHT_BITS)          # conservative: 6554

    def _check(name: str, fan_in: int, label: str):
        nonlocal ok
        max_val = fan_in * x_max * w_max
        limit   = BSGS_LIMIT if label == "BSGS" else INT32_LIMIT
        safe    = max_val < limit
        if not safe:
            ok = False
        rows.append((name, max_val, label, limit, "OK" if safe else "OVERFLOW"))

    # fan-in = C_in × kH × kW
    _check("stem          (3ch,  3×3 )", 3 *3*3,   "BSGS")
    _check("l1 conv       (64ch, 3×3 )", 64*3*3,   "BSGS")
    _check("l2 conv       (128ch,3×3 )", 128*3*3,  "BSGS")
    _check("l3 conv       (256ch,3×3 )", 256*3*3,  "BSGS")
    _check("l4 conv       (512ch,3×3 )", 512*3*3,  "BSGS")
    _check("ds shortcut   (256ch,1×1 )", 256*1*1,  "BSGS")
    _check("linear        (512  )",       512,      "BSGS")
    _check("re-enc after shift",          1,        "INT32")

    if verbose:
        hdr = f"{'Phase':<30} {'Max value':>15} {'Type':>5} {'Result':>8}  limit"
        print(hdr)
        print("-" * 70)
        for name, val, lbl, lim, res in rows:
            print(f"{name:<30} {val:>15.2e} {lbl:>5} {res:>8}  ({lim:.2e})")
    return ok


if __name__ == "__main__":
    print("ResNet18 CIFAR-10 truncation safety check (conservative estimate)")
    print("=" * 70)
    safe = check_bsgs_safety(verbose=True)
    print()
    print("Overall:", "SAFE ✓" if safe else "UNSAFE ✗  (须用真实数据校准验证)")
