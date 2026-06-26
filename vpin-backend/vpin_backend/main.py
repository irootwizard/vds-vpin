"""Entry: python -m vpin_backend.main"""

from __future__ import annotations

import uvicorn

from vpin_backend.api.app import create_app
from vpin_backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "vpin_backend.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
