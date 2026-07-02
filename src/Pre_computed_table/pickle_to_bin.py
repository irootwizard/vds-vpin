"""Convert table.pickle (Python BSGS dict) to table.bin (Rust BSG1 format).

BSG1 binary layout:
  bytes 0..4   magic "BSG1"
  bytes 4..8   m = 3_200_000 (u32 LE)
  bytes 8..16  count (u64 LE)
  bytes 16..   entries: x[32] y[32] j[4] each
"""
import os
import pickle
import struct

script_dir = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(script_dir, "table.pickle")
DST = os.path.join(script_dir, "table.bin")

MAGIC = b"BSG1"
BSGS_M = 3_200_000

print(f"Loading {SRC} ...")
with open(SRC, "rb") as f:
    table: dict = pickle.load(f)

count = len(table)
print(f"  entries: {count}")

with open(DST, "wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", BSGS_M))
    out.write(struct.pack("<Q", count))
    for (x, y), j in table.items():
        # Identity point: ecdsa returns None for x/y — Rust uses all-zeros key
        x_bytes = x.to_bytes(32, "big") if x is not None else b"\x00" * 32
        y_bytes = y.to_bytes(32, "big") if y is not None else b"\x00" * 32
        out.write(x_bytes)
        out.write(y_bytes)
        out.write(struct.pack("<I", j))

size_mb = os.path.getsize(DST) / 1024 / 1024
print(f"Written {DST}  ({size_mb:.1f} MB)")
