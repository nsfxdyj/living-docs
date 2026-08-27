"""Tests for the M5 adversarial-review fixes (C1/C2, M1-M5, m1/m2/m5)."""

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


def _create_document(
    client: TestClient, token: str, workspace_id: int, title: str, content: str = "# hi"
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        json={"title": title, "content_md": content, "tags": []},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fork(client: TestClient, token: str, document_id: int) -> dict:
    response = client.post(
        f"/api/documents/{document_id}/fork", headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _propose(client: TestClient, token: str, source_id: int, target_id: int) -> dict:
    response = client.post(
        f"/api/documents/{source_id}/merge-requests",
        json={"target_doc_id": target_id},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _doc_from_listing(client: TestClient, token: str, wid: int, doc_id: int) -> dict:
    docs = client.get(
        f"/api/workspaces/{wid}/documents", headers=_auth(token)
    ).json()
    return next(d for d in docs if d["id"] == doc_id)


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "fix-owner@example.com", "Fix Owner")


@pytest.fixture(scope="module")
def member(client: TestClient) -> tuple[str, int]:
    return _register(client, "fix-member@example.com", "Fix Member")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner: tuple[str, int], member: tuple[str, int]) -> int:
    owner_token, _ = owner
    response = client.post(
        "/api/workspaces", json={"name": "Fix Team"}, headers=_auth(owner_token)
    )
    wid = response.json()["id"]
    invite = client.post(
        f"/api/workspaces/{wid}/invites", headers=_auth(owner_token)
    ).json()
    joined = client.post(
        "/api/workspaces/join",
        json={"token": invite["token"]},
        headers=_auth(member[0]),
    )
    assert joined.status_code == 200, joined.text
    return wid


# --- C2: fork transfers vitality instead of minting it ----------------------


def test_fork_takes_vitality_from_source(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    owner_token, _ = owner
    doc = _create_document(client, owner_token, workspace_id, "Energy Source")
    for _ in range(2):  # 2 edits * 8 = 16 vitality
        client.patch(
            f"/api/documents/{doc['id']}",
            json={"content_md": "# charged"},
            headers=_auth(owner_token),
        )
    fork = _fork(client, member[0], doc["id"])
    assert fork["vitality"] == 8.0  # half of 16
    # Source: 16 - 8 (taken by the fork) + 10 (fork signal) = 18.
    source = _doc_from_listing(client, owner_token, workspace_id, doc["id"])
    assert source["vitality"] == 18.0


def test_fork_throttled_per_user_per_document(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Throttle Me")
    assert (
        client.post(f"/api/documents/{doc['id']}/fork", headers=_auth(member_token))
        .status_code
        == 201
    )
    # Second fork by the same user within 30 minutes is rejected.
    throttled = client.post(
        f"/api/documents/{doc['id']}/fork", headers=_auth(member_token)
    )
    assert throttled.status_code == 429
    # ... but another user may fork it,
    assert (
        client.post(f"/api/documents/{doc['id']}/fork", headers=_auth(owner_token))
        .status_code
        == 201
    )
    # ... and the same user may fork a different document.
    other = _create_document(client, owner_token, workspace_id, "Other Doc")
    assert (
        client.post(f"/api/documents/{other['id']}/fork", headers=_auth(member_token))
        .status_code
        == 201
    )


# --- C1: vitality can be merged only once -----------------------------------


def _accepted_mr(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], wid: int, title: str
) -> tuple[dict, dict, dict]:
    """Set up trunk -> fork -> accepted merge request; return (trunk, fork, mr)."""
    owner_token, member_token = owner[0], member[0]
    trunk = _create_document(client, owner_token, wid, title, content="# original")
    fork = _fork(client, member_token, trunk["id"])
    client.patch(
        f"/api/documents/{fork['id']}",
        json={"content_md": "# improved"},
        headers=_auth(member_token),
    )
    mr = _propose(client, member_token, fork["id"], trunk["id"])
    accepted = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token)
    )
    assert accepted.status_code == 200, accepted.text
    return trunk, fork, accepted.json()


def test_double_accept_conflict_and_transfers_once(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    trunk, _, mr = _accepted_mr(client, owner, member, workspace_id, "Once Only")
    assert mr["status"] == "accepted"
    assert mr["decided_at"] is not None

    before = _doc_from_listing(client, owner[0], workspace_id, trunk["id"])
    again = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner[0])
    )
    assert again.status_code == 409
    after = _doc_from_listing(client, owner[0], workspace_id, trunk["id"])
    assert after["vitality"] == before["vitality"]


def test_duplicate_open_merge_request_conflict(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    trunk = _create_document(client, owner[0], workspace_id, "Dup Target")
    fork = _fork(client, member[0], trunk["id"])
    _propose(client, member[0], fork["id"], trunk["id"])
    duplicate = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": trunk["id"]},
        headers=_auth(member[0]),
    )
    assert duplicate.status_code == 409


def test_merged_fork_cannot_open_merge_request(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    trunk, fork, _ = _accepted_mr(client, owner, member, workspace_id, "Spent Fork")
    response = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": trunk["id"]},
        headers=_auth(member[0]),
    )
    assert response.status_code == 400


# --- M1: merge direction must point at a strict ancestor --------------------


def test_merge_into_descendant_or_sibling_rejected(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    root = _create_document(client, owner[0], workspace_id, "Direction Root")
    fork_a = _fork(client, member[0], root["id"])
    fork_b = _fork(client, owner[0], fork_a["id"])  # child of fork_a
    fork_c = _fork(client, owner[0], root["id"])  # sibling of fork_a

    # Downwards (into a descendant) is not a merge.
    downwards = client.post(
        f"/api/documents/{fork_a['id']}/merge-requests",
        json={"target_doc_id": fork_b["id"]},
        headers=_auth(member[0]),
    )
    assert downwards.status_code == 400

    # Sideways (same root, not an ancestor) is not a merge either.
    sideways = client.post(
        f"/api/documents/{fork_c['id']}/merge-requests",
        json={"target_doc_id": fork_a["id"]},
        headers=_auth(owner[0]),
    )
    assert sideways.status_code == 400

    # Upwards to the direct parent still works.
    assert (
        client.post(
            f"/api/documents/{fork_b['id']}/merge-requests",
            json={"target_doc_id": fork_a["id"]},
            headers=_auth(owner[0]),
        ).status_code
        == 201
    )


# --- M2 + m1: deletion cascades ----------------------------------------------


def test_deleted_target_orphans_mr_and_breaks_get_diff(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    owner_token, member_token = owner[0], member[0]
    target = _create_document(client, owner_token, workspace_id, "Doomed Target")
    fork = _fork(client, member_token, target["id"])
    mr = _propose(client, member_token, fork["id"], target["id"])

    assert (
        client.delete(f"/api/documents/{target['id']}", headers=_auth(owner_token))
        .status_code
        == 204
    )
    # The open request is marked orphaned instead of being deleted silently.
    listed = client.get(
        f"/api/documents/{fork['id']}/merge-requests", headers=_auth(member_token)
    ).json()
    assert listed[0]["status"] == "orphaned"
    # Endpoints that need both documents now 404 instead of 500.
    assert (
        client.get(
            f"/api/merge-requests/{mr['id']}", headers=_auth(member_token)
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/merge-requests/{mr['id']}/diff", headers=_auth(member_token)
        ).status_code
        == 404
    )


def test_delete_document_detaches_children(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    root = _create_document(client, owner[0], workspace_id, "Detachable Root")
    fork = _fork(client, member[0], root["id"])
    assert (
        client.delete(f"/api/documents/{root['id']}", headers=_auth(owner[0]))
        .status_code
        == 204
    )
    orphan = _doc_from_listing(client, member[0], workspace_id, fork["id"])
    assert orphan["parent_id"] is None


# --- M4: merged documents are frozen -----------------------------------------


def test_merged_document_cannot_be_forked_or_charged(
    client: TestClient, owner: tuple[str, int], member: tuple[str, int], workspace_id: int
) -> None:
    _, fork, _ = _accepted_mr(client, owner, member, workspace_id, "Frozen Fork")

    fork_again = client.post(
        f"/api/documents/{fork['id']}/fork", headers=_auth(owner[0])
    )
    assert fork_again.status_code == 400

    # Viewing and editing a merged document no longer charge it. (The merged
    # fork is hidden from the default listing, so fetch it directly.)
    baseline = client.get(
        f"/api/documents/{fork['id']}?track=false", headers=_auth(owner[0])
    ).json()["vitality"]
    viewed = client.get(f"/api/documents/{fork['id']}", headers=_auth(owner[0]))
    assert viewed.json()["vitality"] == baseline
    edited = client.patch(
        f"/api/documents/{fork['id']}",
        json={"title": "Frozen Fork (edited)"},
        headers=_auth(member[0]),
    )
    assert edited.status_code == 200
    assert edited.json()["vitality"] == baseline
    assert edited.json()["status"] == "merged"


# --- m2: track=false ----------------------------------------------------------


def test_track_false_skips_view_charge(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    owner_token, _ = owner
    doc = _create_document(client, owner_token, workspace_id, "No Tracking")
    untracked = client.get(
        f"/api/documents/{doc['id']}?track=false", headers=_auth(owner_token)
    )
    assert untracked.status_code == 200
    assert untracked.json()["vitality"] == 0

    tracked = client.get(f"/api/documents/{doc['id']}", headers=_auth(owner_token))
    assert tracked.json()["vitality"] == 1

    untracked_again = client.get(
        f"/api/documents/{doc['id']}?track=false", headers=_auth(owner_token)
    )
    assert untracked_again.json()["vitality"] == 1
