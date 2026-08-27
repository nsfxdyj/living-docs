"""Shared pytest fixtures for the backend test suite."""

import os
import tempfile

# Keep tests hermetic: never touch a real on-disk database file or the
# real attachments directory. Must be set before app modules are imported
# (settings are cached).
os.environ.setdefault("LIVING_DOCS_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "LIVING_DOCS_ATTACHMENTS_DIR",
    tempfile.mkdtemp(prefix="living-docs-test-attachments-"),
)

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    # The context manager runs the lifespan, which creates all tables.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module", autouse=True)
def _fresh_db() -> Iterator[None]:
    # Each test module starts from an empty database so tests can rely on
    # fresh state (e.g. "first registered user") regardless of module order.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
