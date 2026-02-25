from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.api.routes import router
from server.runtime import get_state, initialize


def create_app(config_path: str = "config.yaml") -> FastAPI:
    initialize(config_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        state = get_state()
        state.engine.start()
        try:
            yield
        finally:
            state.engine.stop()

    app = FastAPI(title="FPGA Server", lifespan=lifespan)
    app.include_router(router)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
