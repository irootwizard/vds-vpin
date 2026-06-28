"""Pytest path setup for HDC / network_lenet tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "vpin-client", REPO / "vpin-backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
