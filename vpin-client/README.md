# vPIN Client

Independent client package for vPIN protocol compliance: γ sampling, M1 scalar verify, AHE, P6 pipeline.

## Install

```bash
pip install -e vpin-client
```

## CLI

```bash
vpin-client sample-challenge --num-pt-add 2144 --num-pt-mult 178
```

## Upload (A6-2)

Use `vpin_client.upload.upload_model()` against a running FastAPI backend.

## Tests

```bash
pytest vpin-client/tests
```

## Tauri desktop shell (optional, A6-3)

The independent client is designed to run inside a **Tauri 2** host (`localhost:1420` is already allowed in backend CORS). MVP workflow: ship `vpin-client` as a Python sidecar or embed verification via HTTP to `vpin-backend`; a full Tauri UI is optional and not required for protocol compliance tests.
