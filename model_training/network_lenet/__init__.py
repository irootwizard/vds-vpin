"""LeNet-CIFAR training stack — CIFAR-10 3×32×32 HDC validation track (P2).

Mirrors ``model_training/network_a`` but for the ``lenet_cifar`` family:
Conv2d(3,6,5) → 2×2 sum-pool → Conv2d(6,16,5) → 2×2 sum-pool → FC 400→120→84→10,
with truncation phases Π=(π1..π6) derived from the HDC formula (pool from_bits=28,
fc from_bits=32 — NOT Network A's 26).
"""
