"""Shared pytest fixtures for the backend test suite."""

import os

# Keep tests hermetic: never touch a real on-disk database file.
# Must be set before app modules are imported (settings are cached).
os.environ.setdefault("LIVING_DOCS_DATABASE_URL", "sqlite:///:memory:")

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    # The context manager runs the lifespan, which creates all tables.
    with TestClient(app) as test_client:
        yield test_client
