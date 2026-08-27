"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models  # noqa: F401  (register ORM models on the metadata)
from .api import attachments, auth, comments, documents, evolution, health, notifications, search, workspaces
from .config import get_settings
from .db import Base, SessionLocal, engine
from .life import run_decay
from .search import probe_fts5, rebuild_index_if_stale


def _decay_job() -> None:
    """One scheduled decay tick over all documents."""
    with SessionLocal() as session:
        run_decay(session)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # M1: create tables directly; Alembic migrations come in a later milestone.
    Base.metadata.create_all(bind=engine)
    # FTS5 full-text index: probe support once (search degrades to 503 and
    # indexing to warnings if the build lacks FTS5), then rebuild the index
    # if it disagrees with the documents table (legacy rows, tokenizer change).
    with SessionLocal() as session:
        if probe_fts5(session):
            rebuild_index_if_stale(session)
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
app.include_router(search.router, prefix="/api")

# Serve the built frontend (Vite output) when it is available, e.g. in Docker.
# SPA fallback: unknown non-/api paths return index.html so deep links like
# /login or /docs/3 survive a full page reload.
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        # Starlette raises HTTPException(404) for missing paths (fastapi's
        # HTTPException is a subclass, so catching it would NOT work).
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            # Not a real asset — hand the path to the SPA router.
            return await super().get_response("index.html", scope)
        return response


_static_dir = Path(get_settings().static_dir)
if _static_dir.is_dir():
    app.mount("/", SPAStaticFiles(directory=_static_dir, html=True), name="static")
