"""Truncation plan and BSGS/INT32 safety checks for new_lenet (CIFAR-10) AHE pipeline.

LeNet CIFAR-10 AHE flow (identical to MNIST except 3-channel input):
  initial      : client encrypts [1, 3, 32, 32] at f=16
  after_conv1  : server conv1(3→6,5×5) → [1,6,28,28] f=32
                 client: relu + 2×2 avg_pool → [1,6,14,14] + shift 32→16
  after_conv2  : server conv2(6→16,5×5) → [1,16,10,10] f=32
                 client: relu + 2×2 avg_pool → [1,16,5,5] + shift 32→16
  after_c3     : server c3 as FC(400→120) → [1,120] f=32
                 client: relu + shift 32→16
  after_fc4    : server fc4(120→84) → [1,84] f=32
                 client: relu + shift 32→16
  after_fc5    : server fc5(84→10) → [1,10] f=32
                 client: logits_only → argmax

BSGS_LIMIT ≈ 2^43; INT32_LIMIT = 2^31−1
"""

from __future__ import annotations

FIXED_POINT_BITS = 16
WEIGHT_BITS = 16
POST_LAYER_BITS = FIXED_POINT_BITS + WEIGHT_BITS  # 32

POOL_KERNEL = 2

BSGS_LIMIT = 2**43
INT32_LIMIT = 2**31 - 1

# Mirror of LENET_CIFAR in Rust topology.rs
TRUNCATION_PLAN = [
    {
        "phase_id":      "after_conv1",
        "client_action": "relu_pool_shift",
        "shift_bits":    POST_LAYER_BITS,
        "pool_kernel":   POOL_KERNEL,
        "input_shape":   [1, 6, 28, 28],
        "output_shape":  [1, 6, 14, 14],
    },
    {
        "phase_id":      "after_conv2",
        "client_action": "relu_pool_shift",
        "shift_bits":    POST_LAYER_BITS,
        "pool_kernel":   POOL_KERNEL,
        "input_shape":   [1, 16, 10, 10],
        "output_shape":  [1, 16, 5, 5],
    },
    {
        "phase_id":      "after_c3",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
        "input_shape":   [1, 120],
        "output_shape":  [1, 120],
    },
    {
        "phase_id":      "after_fc4",
        "client_action": "relu_then_shift",
        "shift_bits":    POST_LAYER_BITS,
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
    """Estimate worst-case decrypted value magnitudes."""
    ok = True
    rows = []

    def _check(name, max_val, label):
        nonlocal ok
        safe = max_val < BSGS_LIMIT
        if not safe:
            ok = False
        rows.append((name, max_val, label, "OK" if safe else "OVERFLOW"))

    # conv1: Σ_{3×5×5=75} x_f16 * w_f16; x≤65536, w≤6554
    _check("conv1 output (f=32)", 75 * 65536 * 6554, "BSGS")
    # conv2: Σ_{6×5×5=150}
    _check("conv2 output (f=32)", 150 * 65536 * 6554, "BSGS")
    # c3 as FC(400→120)
    _check("c3 output (f=32)",    400 * 65536 * 6554, "BSGS")
    # fc4(120→84)
    _check("fc4 output (f=32)",   120 * 65536 * 6554, "BSGS")
    # fc5(84→10)
    _check("fc5 output (f=32)",    84 * 65536 * 6554, "BSGS")
    _check("re-enc after shift (i32)", 65536,          "INT32")

    if verbose:
        print(f"{'Phase':<30} {'Max value':>15} {'Type':>6} {'Result':>8}")
        print("-" * 65)
        for name, val, lbl, res in rows:
            lim = BSGS_LIMIT if lbl == "BSGS" else INT32_LIMIT
            print(f"{name:<30} {val:>15.2e} {lbl:>6} {res:>8}  (limit {lim:.2e})")
    return ok


def export_truncation_config(out_path) -> dict:
    import json
    config = {
        "model": "lenet_cifar",
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
    print("LeNet CIFAR-10 truncation safety check")
    print("=" * 65)
    safe = check_bsgs_safety(verbose=True)
    print()
    print("Overall:", "SAFE ✓" if safe else "UNSAFE ✗")
