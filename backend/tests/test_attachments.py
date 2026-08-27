"""Tests for image attachment upload, download and abuse protection."""

import pytest
from fastapi.testclient import TestClient

# Minimal byte sequences carrying real image magic bytes.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
GIF_BYTES = b"GIF89a" + b"\x00" * 32


def _register(client: TestClient, email: str, display_name: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": display_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload(
    client: TestClient,
    token: str,
    document_id: int,
    *,
    filename: str,
    content: bytes,
    content_type: str,
):
    return client.post(
        f"/api/documents/{document_id}/attachments",
        files={"file": (filename, content, content_type)},
        headers=_auth(token),
    )


@pytest.fixture(scope="module")
def uploader_token(client: TestClient) -> str:
    return _register(client, "uploader@example.com", "Uploader")


@pytest.fixture(scope="module")
def outsider_token(client: TestClient) -> str:
    return _register(client, "attach-outsider@example.com", "Attach Outsider")


@pytest.fixture(scope="module")
def document_id(client: TestClient, uploader_token: str) -> int:
    workspace = client.post(
        "/api/workspaces", json={"name": "Attach Team"}, headers=_auth(uploader_token)
    ).json()
    document = client.post(
        f"/api/workspaces/{workspace['id']}/documents",
        json={"title": "Illustrated Doc"},
        headers=_auth(uploader_token),
    ).json()
    return document["id"]


def test_upload_image_and_download_it(
    client: TestClient, uploader_token: str, document_id: int
) -> None:
    response = _upload(
        client,
        uploader_token,
        document_id,
        filename="diagram.png",
        content=PNG_BYTES,
        content_type="image/png",
    )
    assert response.status_code == 201, response.text
    url = response.json()["url"]
    assert url.startswith("/api/attachments/")
    assert url.endswith(".png")

    downloaded = client.get(url, headers=_auth(uploader_token))
    assert downloaded.status_code == 200
    assert downloaded.content == PNG_BYTES


def test_gif_upload_accepted(
    client: TestClient, uploader_token: str, document_id: int
) -> None:
    response = _upload(
        client,
        uploader_token,
        document_id,
        filename="anim.gif",
        content=GIF_BYTES,
        content_type="image/gif",
    )
    assert response.status_code == 201, response.text
    assert response.json()["url"].endswith(".gif")


def test_forged_content_type_rejected(
    client: TestClient, uploader_token: str, document_id: int
) -> None:
    # Declared as image/png, but the bytes are not an image at all.
    response = _upload(
        client,
        uploader_token,
        document_id,
        filename="evil.png",
        content=b"MZ this is not an image",
        content_type="image/png",
    )
    assert response.status_code == 400
    assert "Only image uploads" in response.json()["detail"]


def test_non_image_content_type_rejected(
    client: TestClient, uploader_token: str, document_id: int
) -> None:
    # Real PNG bytes, but declared as text/plain.
    response = _upload(
        client,
        uploader_token,
        document_id,
        filename="sneaky.txt",
        content=PNG_BYTES,
        content_type="text/plain",
    )
    assert response.status_code == 400


def test_oversized_upload_rejected(
    client: TestClient, uploader_token: str, document_id: int
) -> None:
    big = PNG_BYTES + b"\x00" * (2 * 1024 * 1024)
    response = _upload(
        client,
        uploader_token,
        document_id,
        filename="huge.png",
        content=big,
        content_type="image/png",
    )
    assert response.status_code == 413


def test_upload_by_non_member_forbidden(
    client: TestClient, outsider_token: str, document_id: int
) -> None:
    response = _upload(
        client,
        outsider_token,
        document_id,
        filename="x.png",
        content=PNG_BYTES,
        content_type="image/png",
    )
    assert response.status_code == 403


def test_download_requires_auth(client: TestClient, uploader_token: str, document_id: int) -> None:
    url = _upload(
        client,
        uploader_token,
        document_id,
        filename="private.png",
        content=PNG_BYTES,
        content_type="image/png",
    ).json()["url"]
    assert client.get(url).status_code == 401


def test_directory_traversal_rejected(client: TestClient, uploader_token: str) -> None:
    for filename in (
        "..%2F..%2Fapp%2Fmain.py",
        "..%2Fsecret.png",
        "sub%2Ffile.png",
    ):
        response = client.get(
            f"/api/attachments/{filename}", headers=_auth(uploader_token)
        )
        assert response.status_code in (400, 404), filename


def test_missing_attachment_is_404(client: TestClient, uploader_token: str) -> None:
    response = client.get(
        "/api/attachments/does-not-exist.png", headers=_auth(uploader_token)
    )
    assert response.status_code == 404
