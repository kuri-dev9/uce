import asyncio
import os

import uvicorn

from app.main import app


def main() -> int:
    config = uvicorn.Config(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8100")),
        log_level=os.getenv("LOG_LEVEL", "info"),
        loop="asyncio",
        lifespan="off",
    )
    server = uvicorn.Server(config)

    try:
        server.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
