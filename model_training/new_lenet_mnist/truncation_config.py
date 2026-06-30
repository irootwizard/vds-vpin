"""Truncation plan and BSGS/INT32 safety checks for new_lenet_mnist AHE pipeline.

LeNet MNIST AHE flow (5 client rounds):
  initial      : client encrypts [1, 1, 32, 32] at f=16
  after_conv1  : server conv1(1→6,5×5) → [1,6,28,28] f=32
                 client: relu + 2×2 avg_pool → [1,6,14,14] + shift 32→16
  after_conv2  : server conv2(6→16,5×5) → [1,16,10,10] f=32
                 client: relu + 2×2 avg_pool → [1,16,5,5] + shift 32→16
  after_c3     : server c3 as FC(400→120) → [1,120] f=32
                 client: relu + shift 32→16
  after_fc4    : server fc4(120→84) → [1,84] f=32
                 client: relu + shift 32→16
  after_fc5    : server fc5(84→10) → [1,10] f=32
                 client: logits_only → argmax

Fixed-point convention:
  f=16 (FIXED_POINT_BITS): re-encrypted values, input encoding
  f=32 (WEIGHT_BITS×2): output of any layer with float weights at f=16

BSGS_LIMIT   ≈ 2^43 ≈ 8.8×10^12  (must hold all decrypted i64 magnitudes)
INT32_LIMIT  = 2^31 − 1           (re-encrypted i32 values after shift)
"""

from __future__ import annotations

FIXED_POINT_BITS = 16
WEIGHT_BITS = 16
POST_LAYER_BITS = FIXED_POINT_BITS + WEIGHT_BITS  # = 32 (scale after float layer)

# Pool divides by pool_size²; for 2×2 pool: effective 2 extra bits removed from value
POOL_KERNEL = 2
POOL_DIV_BITS = 2 * POOL_KERNEL.bit_length() - 2  # rough: log2(pool_kernel²) = 2

BSGS_LIMIT = 2**43
INT32_LIMIT = 2**31 - 1

# Truncation plan — mirrors LENET_MNIST in Rust topology.rs
# (phase_id, client_action, shift_bits, input_shape, output_shape_after_action)
TRUNCATION_PLAN = [
    {
        "phase_id":      "after_conv1",
        "client_action": "relu_pool_shift",
        "shift_bits":    POST_LAYER_BITS,   # 32
        "pool_kernel":   POOL_KERNEL,
        "input_shape":   [1, 6, 28, 28],    # shape sent by server
        "output_shape":  [1, 6, 14, 14],    # shape after relu+pool
    },
    {
        "phase_id":      "after_conv2",
        "client_action": "relu_pool_shift",
        "shift_bits":    POST_LAYER_BITS,   # 32
        "pool_kernel":   POOL_KERNEL,
        "input_shape":   [1, 16, 10, 10],
        "output_shape":  [1, 16, 5, 5],
    },
    {
        "phase_id":      "after_c3",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,   # 32
        "input_shape":   [1, 120],
        "output_shape":  [1, 120],
    },
    {
        "phase_id":      "after_fc4",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,   # 32
        "input_shape":   [1, 84],
        "output_shape":  [1, 84],
    },
    {
        "phase_id":      "after_fc5",
        "client_action": "logits_only",
        "shift_bits":    None,
        "input_shape":   [1, 10],
        "output_shape":  None,
    },
]


def check_bsgs_safety(*, verbose: bool = False) -> bool:
    """Estimate worst-case decrypted value magnitudes and compare to BSGS_LIMIT.

    Uses pessimistic but realistic estimates for normalized input images.
    Input pixels ≈ [0, 1] → at f=16: ≈ [0, 65536].
    Weights ≈ uniform in [-0.1, 0.1] → at f=16: ≈ [-6554, 6554].
    """
    ok = True
    rows = []

    def _check(name, max_val, label):
        nonlocal ok
        safe = max_val < BSGS_LIMIT
        if not safe:
            ok = False
        rows.append((name, max_val, label, "OK" if safe else "OVERFLOW"))

    # conv1: Σ_{1×5×5=25} x_f16 * w_f16; x≤65536, w≤6554, 25 terms
    conv1_max = 25 * 65536 * 6554  # ≈ 1.07×10^10
    _check("conv1 output (f=32)", conv1_max, "BSGS")

    # conv2: Σ_{6×5×5=150} x_f16 * w_f16; x≤65536, w≤6554, 150 terms
    conv2_max = 150 * 65536 * 6554  # ≈ 6.44×10^10
    _check("conv2 output (f=32)", conv2_max, "BSGS")

    # c3 as FC(400→120): Σ_{400} x_f16 * w_f16; after relu+shift x≤65536
    c3_max = 400 * 65536 * 6554    # ≈ 1.72×10^11
    _check("c3 output (f=32)", c3_max, "BSGS")

    # fc4(120→84): after relu+shift input≤65536, 120 terms
    fc4_max = 120 * 65536 * 6554   # ≈ 5.15×10^10
    _check("fc4 output (f=32)", fc4_max, "BSGS")

    # fc5(84→10): same
    fc5_max = 84 * 65536 * 6554    # ≈ 3.61×10^10
    _check("fc5 output (f=32)", fc5_max, "BSGS")

    # Re-encrypted values after shift 32→16: value ≈ x_true * 2^16 ≤ 2^16 for unit input
    reenc_max = 65536  # 2^16
    _check("re-enc after shift (i32)", reenc_max, "INT32")

    if verbose:
        print(f"{'Phase':<30} {'Max value':>15} {'Type':>6} {'Result':>8}")
        print("-" * 65)
        for name, val, lbl, res in rows:
            lim = BSGS_LIMIT if lbl == "BSGS" else INT32_LIMIT
            print(f"{name:<30} {val:>15.2e} {lbl:>6} {res:>8}  (limit {lim:.2e})")
    return ok


def export_truncation_config(out_path) -> dict:
    """Return and optionally save the truncation config as JSON."""
    import json
    config = {
        "model": "lenet_mnist",
        "fixed_point_bits": FIXED_POINT_BITS,
        "weight_bits": WEIGHT_BITS,
        "bsgs_limit": BSGS_LIMIT,
        "int32_limit": INT32_LIMIT,
        "truncation_plan": TRUNCATION_PLAN,
    }
    out_path = __import__("pathlib").Path(out_path)
    out_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


if __name__ == "__main__":
    print("LeNet MNIST truncation safety check")
    print("=" * 65)
    safe = check_bsgs_safety(verbose=True)
    print()
    print("Overall:", "SAFE ✓" if safe else "UNSAFE ✗")
