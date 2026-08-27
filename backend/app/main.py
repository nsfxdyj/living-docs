"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register ORM models on the metadata)
from .api import attachments, auth, comments, documents, evolution, health, notifications, workspaces
from .config import get_settings
from .db import Base, SessionLocal, engine
from .life import run_decay


def _decay_job() -> None:
    """One scheduled decay tick over all documents."""
    with SessionLocal() as session:
        run_decay(session)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # M1: create tables directly; Alembic migrations come in a later milestone.
    Base.metadata.create_all(bind=engine)
    # M4: background vitality decay (default: every 24h, factor 0.95).
    settings = get_settings()
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _decay_job,
        trigger="interval",
        hours=settings.decay_interval_hours,
        id="vitality-decay",
    )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Living Docs", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(evolution.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")

# Serve the built frontend (Vite output) when it is available, e.g. in Docker.
_static_dir = Path(get_settings().static_dir)
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
