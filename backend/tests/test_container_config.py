"""Deployment configuration regression tests."""

from pathlib import Path


def test_image_stores_attachments_on_persistent_data_volume() -> None:
    dockerfile = (Path(__file__).parents[2] / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "LIVING_DOCS_ATTACHMENTS_DIR=/data/attachments" in dockerfile
