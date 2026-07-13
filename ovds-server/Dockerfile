# OVDS / VADS Python reference — reproducible charm-crypto (BN254) environment.
# Replaces manual WSL setup: crypto-libs/local_install (PBC) + crypto-libs-venv (charm 0.50).

FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    m4 \
    flex \
    bison \
    libgmp-dev \
    libssl-dev \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# PBC 0.5.14 (Debian bookworm has no libpbc-dev; build from Stanford mirror)
ARG PBC_VERSION=0.5.14
RUN wget -O "pbc-${PBC_VERSION}.tar.gz" \
      "https://crypto.stanford.edu/pbc/files/pbc-${PBC_VERSION}.tar.gz" \
    && tar xzf "pbc-${PBC_VERSION}.tar.gz" \
    && cd "pbc-${PBC_VERSION}" \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cd .. \
    && rm -rf "pbc-${PBC_VERSION}" "pbc-${PBC_VERSION}.tar.gz"

# Charm-Crypto 0.50 is not on PyPI (only 0.43); build from source like crypto-libs/charm
RUN pip install --no-cache-dir "pyparsing>=2.1.5,<2.4.1" hypothesis setuptools \
    && git clone --depth 1 --branch dev https://github.com/JHUISI/charm.git /tmp/charm \
    && cd /tmp/charm \
    && ./configure.sh \
    && pip install --no-cache-dir . \
    && rm -rf /tmp/charm

RUN python -c "\
from charm.toolbox.pairinggroup import PairingGroup, G1, G2, GT, ZR, pair; \
g = PairingGroup('BN254'); \
print('charm BN254 ok', g) \
"

WORKDIR /app

COPY src/ ./src/
COPY RSA-accumulator/ ./RSA-accumulator/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src:/app/RSA-accumulator
ENV PYTHONUNBUFFERED=1

# Default: charm smoke test (full protocol: docker run ... python src/test/test_all.py)
CMD ["python", "scripts/verify_charm.py"]
