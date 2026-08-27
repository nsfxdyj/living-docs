"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register ORM models on the metadata)
from .api import auth, health, workspaces
from .config import get_settings
from .db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # M1: create tables directly; Alembic migrations come in a later milestone.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Living Docs", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")

# Serve the built frontend (Vite output) when it is available, e.g. in Docker.
_static_dir = Path(get_settings().static_dir)
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
