"""Tests for @mention notifications in comments."""

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


def _notifications(client: TestClient, token: str) -> list[dict]:
    response = client.get("/api/notifications", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "mention-owner@example.com", "Mention Owner")


@pytest.fixture(scope="module")
def member(client: TestClient) -> tuple[str, int]:
    return _register(client, "mention-member@example.com", "Mention Member")


@pytest.fixture(scope="module")
def third(client: TestClient) -> tuple[str, int]:
    return _register(client, "mention-third@example.com", "Third Person")


@pytest.fixture(scope="module")
def workspace_id(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    third: tuple[str, int],
) -> int:
    wid = _create_workspace(client, owner[0], "Mention Team")
    _join_workspace(client, owner[0], member[0], wid)
    _join_workspace(client, owner[0], third[0], wid)
    return wid


def test_mention_notifies_member(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Mentioned Doc")

    _post_comment(client, owner_token, doc["id"], "hey @Mention Member, take a look")

    mentions = [n for n in _notifications(client, member_token) if n["kind"] == "mention"]
    assert len(mentions) == 1
    payload = mentions[0]["payload"]
    assert payload["document_id"] == doc["id"]
    assert payload["document_title"] == "Mentioned Doc"
    assert payload["actor_name"] == "Mention Owner"
    assert "comment_id" in payload

    # The commenter gets nothing (no self-notification).
    assert _notifications(client, owner_token) == []


def test_multiple_mentions(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    third: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    third_token, _ = third
    doc = _create_document(client, owner_token, workspace_id, "Multi Mention Doc")

    _post_comment(
        client,
        owner_token,
        doc["id"],
        "@Mention Member and @Third Person please review",
    )

    for token in (member_token, third_token):
        mentions = [
            n
            for n in _notifications(client, token)
            if n["kind"] == "mention"
            and n["payload"]["document_id"] == doc["id"]
        ]
        assert len(mentions) == 1


def test_unknown_name_not_notified(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Ghost Mention Doc")

    before = len(_notifications(client, member_token))
    _post_comment(client, owner_token, doc["id"], "@Nobody Here does not exist")
    after = _notifications(client, member_token)
    # Only the comment notification for the author flow applies; the member
    # must not receive a mention.
    assert all(
        n["kind"] != "mention" or n["payload"]["document_id"] != doc["id"]
        for n in after
    )
    assert len(after) == before


def test_mentioned_author_gets_mention_only(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Author Mention Doc")

    _post_comment(client, member_token, doc["id"], "@Mention Owner what do you think?")

    kinds = [
        n["kind"]
        for n in _notifications(client, owner_token)
        if n["payload"].get("document_id") == doc["id"]
    ]
    assert kinds == ["mention"]


def test_exact_name_matching(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    owner_token, _ = owner
    alice_token, _ = _register(client, "mention-alice@example.com", "Alice")
    al_token, _ = _register(client, "mention-al@example.com", "Al")
    _join_workspace(client, owner_token, alice_token, workspace_id)
    _join_workspace(client, owner_token, al_token, workspace_id)

    doc = _create_document(client, owner_token, workspace_id, "Boundary Doc")
    _post_comment(client, owner_token, doc["id"], "@Alice hello")

    # "Al" is not mentioned by "@Alice" (trailing word-char boundary).
    assert all(n["kind"] != "mention" for n in _notifications(client, al_token))
    assert any(n["kind"] == "mention" for n in _notifications(client, alice_token))


def test_leading_boundary_blocks_email_like_text(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    """``x@Mention Member`` (e.g. inside an email address) is not a mention."""
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Email Doc")
    _post_comment(client, owner_token, doc["id"], "reach me at x@Mention Member ok")

    assert all(
        n["kind"] != "mention" or n["payload"].get("document_id") != doc["id"]
        for n in _notifications(client, member_token)
    )


def test_ambiguous_display_name_notifies_nobody(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    """Two members with the exact same display_name: @name notifies NOBODY."""
    owner_token, _ = owner
    twin1_token, _ = _register(client, "mention-twin1@example.com", "Twin")
    twin2_token, _ = _register(client, "mention-twin2@example.com", "Twin")
    _join_workspace(client, owner_token, twin1_token, workspace_id)
    _join_workspace(client, owner_token, twin2_token, workspace_id)

    doc = _create_document(client, owner_token, workspace_id, "Ambiguous Doc")
    _post_comment(client, owner_token, doc["id"], "@Twin which one are you?")

    for token in (twin1_token, twin2_token):
        assert all(
            n["kind"] != "mention" for n in _notifications(client, token)
        )


def test_display_name_validation(client: TestClient) -> None:
    base = {"email": "x@example.com", "password": "password123"}
    # '@' would break mention parsing.
    bad_at = client.post(
        "/api/auth/register", json={**base, "email": "bad-at@example.com", "display_name": "bad@name"}
    )
    assert bad_at.status_code == 422
    # Control characters could smuggle markup into the UI.
    bad_ctrl = client.post(
        "/api/auth/register",
        json={**base, "email": "bad-ctrl@example.com", "display_name": "bad" + chr(0) + "name"},
    )
    assert bad_ctrl.status_code == 422
    # Length limits: 1..40.
    too_long = client.post(
        "/api/auth/register",
        json={**base, "email": "bad-long@example.com", "display_name": "n" * 41},
    )
    assert too_long.status_code == 422
    empty = client.post(
        "/api/auth/register",
        json={**base, "email": "bad-empty@example.com", "display_name": ""},
    )
    assert empty.status_code == 422
    ok = client.post(
        "/api/auth/register",
        json={**base, "email": "good-name@example.com", "display_name": "n" * 40},
    )
    assert ok.status_code == 201, ok.text


def test_mention_throttled_per_actor_target_document(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    """Same (actor, target, document): only the first mention within 10 min notifies."""
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Throttle Doc")

    _post_comment(client, owner_token, doc["id"], "@Mention Member first ping")
    _post_comment(client, owner_token, doc["id"], "@Mention Member second ping")

    mentions = [
        n
        for n in _notifications(client, member_token)
        if n["kind"] == "mention" and n["payload"].get("document_id") == doc["id"]
    ]
    assert len(mentions) == 1

    # A different document is a different throttle bucket.
    other = _create_document(client, owner_token, workspace_id, "Other Throttle Doc")
    _post_comment(client, owner_token, other["id"], "@Mention Member hello again")
    mentions_other = [
        n
        for n in _notifications(client, member_token)
        if n["kind"] == "mention" and n["payload"].get("document_id") == other["id"]
    ]
    assert len(mentions_other) == 1
