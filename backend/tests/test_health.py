"""Smoke tests for the M1 skeleton."""

import os

# Keep tests hermetic: never touch a real on-disk database file.
os.environ.setdefault("LIVING_DOCS_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
