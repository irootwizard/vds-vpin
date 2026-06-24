"""Minimal FastAPI app without model bootstrap for testing."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vpin_backend.api.routes import data

app = FastAPI(
    title="vPIN Backend (Minimal)",
    version="0.1.0-minimal",
    description="Minimal vPIN backend without model bootstrap for testing",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include only data routes for AHE Demo testing
app.include_router(data.router, prefix="/api/v1")

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "mode": "minimal"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)