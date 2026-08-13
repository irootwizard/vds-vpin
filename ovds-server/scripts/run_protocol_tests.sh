#!/usr/bin/env bash
# Run OVDS VADS protocol integration tests (requires charm; use inside Docker image).
set -euo pipefail
cd /app
export PYTHONPATH=/app/src:/app/RSA-accumulator
exec python src/test/test_all.py
