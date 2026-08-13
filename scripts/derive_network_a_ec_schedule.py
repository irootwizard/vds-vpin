#!/usr/bin/env python3
"""Thin wrapper: derive EC witness schedule for standard model_training Network A."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from model_training.network_a.ec_witness_schedule import main

if __name__ == "__main__":
    raise SystemExit(main())
