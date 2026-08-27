"""Tests for M6 notifications: generation triggers, read markers and SSE."""

import json
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.main import app


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


def _notifications(client: TestClient, token: str) -> list[dict]:
    response = client.get("/api/notifications", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _fork_and_propose(
    client: TestClient, token: str, trunk_id: int
) -> tuple[dict, dict]:
    fork = client.post(f"/api/documents/{trunk_id}/fork", headers=_auth(token))
    assert fork.status_code == 201, fork.text
    mr = client.post(
        f"/api/documents/{fork.json()['id']}/merge-requests",
        json={"target_doc_id": trunk_id},
        headers=_auth(token),
    )
    assert mr.status_code == 201, mr.text
    return fork.json(), mr.json()


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "notif-owner@example.com", "Notif Owner")


@pytest.fixture(scope="module")
def member(client: TestClient) -> tuple[str, int]:
    return _register(client, "notif-member@example.com", "Notif Member")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner: tuple[str, int], member: tuple[str, int]) -> int:
    wid = _create_workspace(client, owner[0], "Notif Team")
    _join_workspace(client, owner[0], member[0], wid)
    return wid


def test_comment_notification(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, owner_id = owner
    member_token, member_id = member
    doc = _create_document(client, owner_token, workspace_id, "Notif Comment Doc")

    # Someone else comments on my document -> I get a notification.
    response = client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "Nice doc!"},
        headers=_auth(member_token),
    )
    assert response.status_code == 201, response.text

    mine = _notifications(client, owner_token)
    assert len(mine) == 1
    notif = mine[0]
    assert notif["kind"] == "comment"
    assert notif["read"] is False
    assert notif["workspace_id"] == workspace_id
    assert notif["payload"]["document_id"] == doc["id"]
    assert notif["payload"]["document_title"] == "Notif Comment Doc"
    assert notif["payload"]["comment_id"] == response.json()["id"]
    assert notif["payload"]["actor_id"] == member_id
    assert notif["payload"]["actor_name"] == "Notif Member"

    # The commenter (and a third party) get nothing.
    assert _notifications(client, member_token) == []

    # Commenting on my own document does not notify me.
    client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "talking to myself"},
        headers=_auth(owner_token),
    )
    assert len(_notifications(client, owner_token)) == 1
    assert owner_id is not None  # fixture sanity


def test_merge_request_notifications(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    trunk = _create_document(client, owner_token, workspace_id, "Notif Merge Trunk")

    # Merge request created -> target author is notified.
    _, mr = _fork_and_propose(client, member_token, trunk["id"])
    mine = _notifications(client, owner_token)
    created = [n for n in mine if n["kind"] == "merge_request"]
    assert len(created) == 1
    assert created[0]["payload"]["merge_request_id"] == mr["id"]
    assert created[0]["payload"]["target_doc_id"] == trunk["id"]
    assert created[0]["payload"]["actor_name"] == "Notif Member"

    # Accepted -> the proposer is notified.
    response = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token)
    )
    assert response.status_code == 200, response.text
    theirs = _notifications(client, member_token)
    accepted = [n for n in theirs if n["kind"] == "merge_accepted"]
    assert len(accepted) == 1
    assert accepted[0]["payload"]["merge_request_id"] == mr["id"]
    assert accepted[0]["payload"]["actor_name"] == "Notif Owner"

    # Rejected -> the proposer is notified too. (A second trunk: the same
    # user may fork the same document only once per 30 minutes.)
    trunk2 = _create_document(client, owner_token, workspace_id, "Notif Merge Trunk 2")
    _, mr2 = _fork_and_propose(client, member_token, trunk2["id"])
    response = client.post(
        f"/api/merge-requests/{mr2['id']}/reject", headers=_auth(owner_token)
    )
    assert response.status_code == 200, response.text
    theirs = _notifications(client, member_token)
    rejected = [n for n in theirs if n["kind"] == "merge_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["payload"]["merge_request_id"] == mr2["id"]

    # Newest first ordering.
    ids = [n["id"] for n in theirs]
    assert ids == sorted(ids, reverse=True)


def test_no_self_notification_for_merge(
    client: TestClient,
    owner: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    before = len(_notifications(client, owner_token))
    trunk = _create_document(client, owner_token, workspace_id, "Self Merge Trunk")
    # The owner proposes and decides their own merge: no self notifications.
    _, mr = _fork_and_propose(client, owner_token, trunk["id"])
    client.post(f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token))
    assert len(_notifications(client, owner_token)) == before


def test_read_markers(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, owner_id = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Read Markers Doc")
    client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "ping"},
        headers=_auth(member_token),
    )
    notif = _notifications(client, owner_token)[0]
    assert notif["read"] is False

    # Marking a single notification read.
    assert (
        client.post(
            f"/api/notifications/{notif['id']}/read", headers=_auth(owner_token)
        ).status_code
        == 204
    )
    assert _notifications(client, owner_token)[0]["read"] is True

    # Cannot touch someone else's (or a missing) notification.
    assert (
        client.post(
            f"/api/notifications/{notif['id']}/read", headers=_auth(member_token)
        ).status_code
        == 404
    )
    assert (
        client.post("/api/notifications/999999/read", headers=_auth(owner_token))
        .status_code
        == 404
    )

    # read-all clears everything unread.
    client.post(
        f"/api/documents/{doc['id']}/comments",
        json={"body": "ping again"},
        headers=_auth(member_token),
    )
    assert any(not n["read"] for n in _notifications(client, owner_token))
    assert (
        client.post("/api/notifications/read-all", headers=_auth(owner_token))
        .status_code
        == 204
    )
    assert all(n["read"] for n in _notifications(client, owner_token))

    # Unauthenticated access is rejected.
    assert client.get("/api/notifications").status_code == 401
    assert client.post("/api/notifications/read-all").status_code == 401
    assert owner_id is not None  # fixture sanity


def test_sse_stream_requires_auth(client: TestClient) -> None:
    assert client.get("/api/notifications/stream").status_code == 401
    assert (
        client.get("/api/notifications/stream", params={"token": "bogus"}).status_code
        == 401
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_server() -> Iterator[str]:
    """Run the app under a real uvicorn server (in a thread).

    The Starlette TestClient does not deliver streaming responses
    incrementally, so the SSE push test needs a real HTTP server.
    """
    config = uvicorn.Config(
        app, host="127.0.0.1", port=_free_port(), log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("live server did not start")
    yield f"http://127.0.0.1:{config.port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_sse_stream_pushes_notification(live_server: str) -> None:
    with httpx.Client(base_url=live_server, timeout=10) as http:
        author = http.post(
            "/api/auth/register",
            json={
                "email": "sse-author@example.com",
                "password": "password123",
                "display_name": "SSE Author",
            },
        ).json()
        commenter = http.post(
            "/api/auth/register",
            json={
                "email": "sse-commenter@example.com",
                "password": "password123",
                "display_name": "SSE Commenter",
            },
        ).json()
        author_headers = {"Authorization": f"Bearer {author['token']}"}
        commenter_headers = {"Authorization": f"Bearer {commenter['token']}"}
        wid = http.post(
            "/api/workspaces", json={"name": "SSE Team"}, headers=author_headers
        ).json()["id"]
        invite = http.post(
            f"/api/workspaces/{wid}/invites", headers=author_headers
        ).json()
        http.post(
            "/api/workspaces/join",
            json={"token": invite["token"]},
            headers=commenter_headers,
        )
        doc = http.post(
            f"/api/workspaces/{wid}/documents",
            json={"title": "SSE Doc"},
            headers=author_headers,
        ).json()

        # EventSource-style auth: the JWT travels as a ?token= query param.
        with http.stream(
            "GET", "/api/notifications/stream", params={"token": author["token"]}
        ) as stream:
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            # iter_lines also yields the blank lines separating SSE messages.
            lines = (line for line in stream.iter_lines() if line != "")
            # The stream opens with a comment line immediately.
            assert next(lines) == ": connected"

            # Trigger a notification: someone comments on the author's doc.
            created = http.post(
                f"/api/documents/{doc['id']}/comments",
                json={"body": "live update"},
                headers=commenter_headers,
            )
            assert created.status_code == 201, created.text

            event_line = next(lines)
            data_line = next(lines)
            assert event_line == "event: notification"
            event = json.loads(data_line.removeprefix("data:").strip())
            assert event["kind"] == "comment"
            assert event["payload"]["document_id"] == doc["id"]
            assert event["payload"]["actor_name"] == "SSE Commenter"
            assert event["read"] is False
