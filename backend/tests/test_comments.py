"""Tests for M6 comments: CRUD, permissions and vitality charging."""

import pytest
from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, display_name: str) -> tuple[str, int]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": display_name,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data["token"], data["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace(client: TestClient, token: str, name: str) -> int:
    response = client.post("/api/workspaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _join_workspace(client: TestClient, owner_token: str, token: str, wid: int) -> None:
    invite = client.post(
        f"/api/workspaces/{wid}/invites", headers=_auth(owner_token)
    ).json()
    joined = client.post(
        "/api/workspaces/join",
        json={"token": invite["token"]},
        headers=_auth(token),
    )
    assert joined.status_code == 200, joined.text


def _create_document(client: TestClient, token: str, workspace_id: int, title: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        json={"title": title, "content_md": "# hello"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _post_comment(client: TestClient, token: str, doc_id: int, body: str) -> dict:
    response = client.post(
        f"/api/documents/{doc_id}/comments",
        json={"body": body},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _list_comments(client: TestClient, token: str, doc_id: int) -> list[dict]:
    response = client.get(f"/api/documents/{doc_id}/comments", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _workspace_doc(client: TestClient, token: str, wid: int, doc_id: int) -> dict:
    """Fetch a document via the workspace listing (no view interaction charged)."""
    docs = client.get(f"/api/workspaces/{wid}/documents", headers=_auth(token)).json()
    return next(d for d in docs if d["id"] == doc_id)


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "comments-owner@example.com", "Comments Owner")


@pytest.fixture(scope="module")
def member(client: TestClient) -> tuple[str, int]:
    return _register(client, "comments-member@example.com", "Comments Member")


@pytest.fixture(scope="module")
def outsider(client: TestClient) -> tuple[str, int]:
    return _register(client, "comments-outsider@example.com", "Comments Outsider")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner: tuple[str, int], member: tuple[str, int]) -> int:
    wid = _create_workspace(client, owner[0], "Comments Team")
    _join_workspace(client, owner[0], member[0], wid)
    return wid


def test_create_comment_charges_vitality(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, member_id = member
    doc = _create_document(client, owner_token, workspace_id, "Commented Doc")

    comment = _post_comment(client, member_token, doc["id"], "First!")
    assert comment["document_id"] == doc["id"]
    assert comment["body"] == "First!"
    assert comment["author"]["id"] == member_id
    assert comment["author"]["display_name"] == "Comments Member"
    assert "created_at" in comment

    # comment energy = +5 (see app/life.py INTERACTION_ENERGY).
    state = _workspace_doc(client, owner_token, workspace_id, doc["id"])
    assert state["vitality"] == 5.0

    _post_comment(client, owner_token, doc["id"], "Second comment")
    state = _workspace_doc(client, owner_token, workspace_id, doc["id"])
    assert state["vitality"] == 10.0


def test_list_comments_chronological(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Chronology Doc")
    first = _post_comment(client, owner_token, doc["id"], "one")
    second = _post_comment(client, member_token, doc["id"], "two")
    third = _post_comment(client, owner_token, doc["id"], "three")

    comments = _list_comments(client, member_token, doc["id"])
    assert [c["id"] for c in comments] == [first["id"], second["id"], third["id"]]
    assert [c["body"] for c in comments] == ["one", "two", "three"]


def test_comment_validation_and_access(
    client: TestClient,
    owner: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    outsider_token, _ = outsider
    doc = _create_document(client, owner_token, workspace_id, "Guarded Doc")

    # Unauthenticated: 401.
    assert client.post(
        f"/api/documents/{doc['id']}/comments", json={"body": "hi"}
    ).status_code == 401
    assert client.get(f"/api/documents/{doc['id']}/comments").status_code == 401

    # Non-member: 403.
    denied = client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "hi"},
        headers=_auth(outsider_token),
    )
    assert denied.status_code == 403
    denied = client.get(
        f"/api/documents/{doc['id']}/comments", headers=_auth(outsider_token)
    )
    assert denied.status_code == 403

    # Body limits: empty and over 2000 chars are rejected.
    empty = client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": ""},
        headers=_auth(owner_token),
    )
    assert empty.status_code == 422
    too_long = client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "x" * 2001},
        headers=_auth(owner_token),
    )
    assert too_long.status_code == 422
    at_limit = client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "x" * 2000},
        headers=_auth(owner_token),
    )
    assert at_limit.status_code == 201

    # Missing document: 404.
    missing = client.post(
        "/api/documents/999999/comments",
        json={"body": "hi"},
        headers=_auth(owner_token),
    )
    assert missing.status_code == 404


def test_delete_comment_permissions(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    outsider_token, _ = outsider
    doc = _create_document(client, owner_token, workspace_id, "Deletion Doc")
    by_owner = _post_comment(client, owner_token, doc["id"], "owner's comment")
    by_member = _post_comment(client, member_token, doc["id"], "member's comment")

    # A different member (not the author, not the owner) cannot delete.
    other_token, _ = _register(client, "comments-other@example.com", "Other Member")
    _join_workspace(client, owner_token, other_token, workspace_id)
    denied = client.delete(
        f"/api/comments/{by_owner['id']}", headers=_auth(other_token)
    )
    assert denied.status_code == 403

    # Non-members get 403 too; unauthenticated gets 401; unknown id gets 404.
    denied = client.delete(
        f"/api/comments/{by_owner['id']}", headers=_auth(outsider_token)
    )
    assert denied.status_code == 403
    assert client.delete(f"/api/comments/{by_owner['id']}").status_code == 401
    assert (
        client.delete("/api/comments/999999", headers=_auth(owner_token)).status_code
        == 404
    )

    # The author can delete their own comment.
    deleted = client.delete(
        f"/api/comments/{by_member['id']}", headers=_auth(member_token)
    )
    assert deleted.status_code == 204

    # The workspace owner can delete anyone's comment.
    deleted = client.delete(
        f"/api/comments/{by_owner['id']}", headers=_auth(owner_token)
    )
    assert deleted.status_code == 204

    assert _list_comments(client, owner_token, doc["id"]) == []
