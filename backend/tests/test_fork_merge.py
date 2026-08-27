"""Tests for M5: fork, merge requests, diff and the evolution tree."""

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


def _create_document(
    client: TestClient,
    token: str,
    workspace_id: int,
    title: str,
    content_md: str = "# hello",
    tags: list[str] | None = None,
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        json={"title": title, "content_md": content_md, "tags": tags or ["note"]},
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


def _propose_merge(
    client: TestClient, token: str, source_id: int, target_id: int
) -> dict:
    response = client.post(
        f"/api/documents/{source_id}/merge-requests",
        json={"target_doc_id": target_id},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _workspace_doc(client: TestClient, token: str, wid: int, doc_id: int) -> dict:
    """Fetch a document via the workspace listing (no view interaction charged)."""
    docs = client.get(
        f"/api/workspaces/{wid}/documents", headers=_auth(token)
    ).json()
    return next(d for d in docs if d["id"] == doc_id)


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "evo-owner@example.com", "Evo Owner")


@pytest.fixture(scope="module")
def member(client: TestClient) -> tuple[str, int]:
    return _register(client, "evo-member@example.com", "Evo Member")


@pytest.fixture(scope="module")
def outsider(client: TestClient) -> tuple[str, int]:
    return _register(client, "evo-outsider@example.com", "Evo Outsider")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner: tuple[str, int], member: tuple[str, int]) -> int:
    wid = _create_workspace(client, owner[0], "Evolution Team")
    _join_workspace(client, owner[0], member[0], wid)
    return wid


def test_fork_inherits_and_charges_source(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, member_id = member
    doc = _create_document(
        client, owner_token, workspace_id, "Root Doc", content_md="# v1", tags=["guide"]
    )
    # Charge the source a bit so the fork has something to inherit (edit = 8).
    client.patch(
        f"/api/documents/{doc['id']}",
        json={"content_md": "# v1"},
        headers=_auth(owner_token),
    )

    fork = _fork(client, member_token, doc["id"])
    assert fork["parent_id"] == doc["id"]
    assert fork["title"] == "Root Doc (fork)"
    assert fork["content_md"] == "# v1"
    assert fork["tags"] == ["guide"]
    assert fork["author_id"] == member_id
    assert fork["workspace_id"] == workspace_id
    # Inherits 50% of the source's 8 vitality and the status is recomputed.
    assert fork["vitality"] == 4.0
    assert fork["status"] == "withered"

    # The fork charges the SOURCE document (fork energy = 10) but takes its
    # inherited vitality out of it: 8 - 4 + 10 = 14.
    source = _workspace_doc(client, owner_token, workspace_id, doc["id"])
    assert source["vitality"] == 14.0


def test_fork_vitality_capped_at_30(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    owner_token, _ = owner
    doc = _create_document(client, owner_token, workspace_id, "Hot Doc")
    for _ in range(8):  # 8 edits * 8 energy = 64 vitality
        client.patch(
            f"/api/documents/{doc['id']}",
            json={"content_md": "# hot"},
            headers=_auth(owner_token),
        )
    fork = _fork(client, owner_token, doc["id"])
    assert fork["vitality"] == 30.0  # 50% of 64 = 32, capped at 30
    assert fork["status"] == "stable"


def test_fork_requires_membership(
    client: TestClient,
    owner: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    outsider_token, _ = outsider
    doc = _create_document(client, owner_token, workspace_id, "Members Only")
    assert client.post(f"/api/documents/{doc['id']}/fork").status_code == 401
    denied = client.post(
        f"/api/documents/{doc['id']}/fork", headers=_auth(outsider_token)
    )
    assert denied.status_code == 403


def test_merge_request_creation_and_validation(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, member_id = member
    outsider_token, _ = outsider
    trunk = _create_document(client, owner_token, workspace_id, "Trunk")
    fork = _fork(client, member_token, trunk["id"])

    mr = _propose_merge(client, member_token, fork["id"], trunk["id"])
    assert mr["status"] == "open"
    assert mr["source_doc_id"] == fork["id"]
    assert mr["target_doc_id"] == trunk["id"]
    assert mr["proposer_id"] == member_id

    # Both the source and the target list the request.
    for doc_id in (fork["id"], trunk["id"]):
        listed = client.get(
            f"/api/documents/{doc_id}/merge-requests", headers=_auth(member_token)
        )
        assert listed.status_code == 200
        assert [m["id"] for m in listed.json()] == [mr["id"]]

    # A trunk document cannot propose a merge.
    not_a_fork = client.post(
        f"/api/documents/{trunk['id']}/merge-requests",
        json={"target_doc_id": fork["id"]},
        headers=_auth(owner_token),
    )
    assert not_a_fork.status_code == 400

    # Cannot merge into itself.
    itself = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": fork["id"]},
        headers=_auth(member_token),
    )
    assert itself.status_code == 400

    # Target must live in the same workspace.
    other_wid = _create_workspace(client, owner_token, "Other Team")
    foreign = _create_document(client, owner_token, other_wid, "Foreign Doc")
    cross_ws = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": foreign["id"]},
        headers=_auth(member_token),
    )
    assert cross_ws.status_code == 400

    # Target must be an ancestor or share the fork's root.
    unrelated = _create_document(client, owner_token, workspace_id, "Unrelated Root")
    bad_target = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": unrelated["id"]},
        headers=_auth(member_token),
    )
    assert bad_target.status_code == 400

    # Non-members cannot propose merges.
    denied = client.post(
        f"/api/documents/{fork['id']}/merge-requests",
        json={"target_doc_id": trunk["id"]},
        headers=_auth(outsider_token),
    )
    assert denied.status_code == 403

    # A fork-of-a-fork may target a higher ancestor (the trunk).
    grandchild = _fork(client, owner_token, fork["id"])
    sibling_mr = client.post(
        f"/api/documents/{grandchild['id']}/merge-requests",
        json={"target_doc_id": trunk["id"]},
        headers=_auth(owner_token),
    )
    assert sibling_mr.status_code == 201


def test_merge_request_diff(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    trunk = _create_document(
        client, owner_token, workspace_id, "Diff Base", content_md="line one\nline two"
    )
    fork = _fork(client, member_token, trunk["id"])
    client.patch(
        f"/api/documents/{fork['id']}",
        json={"content_md": "line one\nline CHANGED\nline three"},
        headers=_auth(member_token),
    )
    mr = _propose_merge(client, member_token, fork["id"], trunk["id"])

    response = client.get(f"/api/merge-requests/{mr['id']}/diff", headers=_auth(member_token))
    assert response.status_code == 200
    diff = response.text
    assert "---" in diff and "+++" in diff
    assert "-line two" in diff
    assert "+line CHANGED" in diff
    assert "+line three" in diff
    assert " line one" in diff  # unchanged context line


def test_accept_merges_content_and_vitality(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(
        client, owner_token, workspace_id, "Merge Target", content_md="# original"
    )
    client.patch(
        f"/api/documents/{doc['id']}",
        json={"content_md": "# original"},
        headers=_auth(owner_token),
    )  # source vitality: 8
    fork = _fork(client, member_token, doc["id"])  # source: 8-4+10=14, fork: 4
    client.patch(
        f"/api/documents/{fork['id']}",
        json={"content_md": "# improved"},
        headers=_auth(member_token),
    )  # fork vitality: 12
    mr = _propose_merge(client, member_token, fork["id"], doc["id"])

    # The proposer is neither target author nor workspace owner: cannot accept.
    denied = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(member_token)
    )
    assert denied.status_code == 403

    accepted = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token)
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    # Target got the fork's content and 50% of its vitality: 14 + 6.
    target = _workspace_doc(client, owner_token, workspace_id, doc["id"])
    assert target["content_md"] == "# improved"
    assert target["vitality"] == 20.0

    # The merged fork is archived: status sticks even when viewed, and it is
    # hidden from the default workspace listing.
    merged = client.get(f"/api/documents/{fork['id']}", headers=_auth(member_token))
    assert merged.json()["status"] == "merged"
    default_ids = [
        d["id"]
        for d in client.get(
            f"/api/workspaces/{workspace_id}/documents", headers=_auth(owner_token)
        ).json()
    ]
    assert fork["id"] not in default_ids
    merged_only = client.get(
        f"/api/workspaces/{workspace_id}/documents",
        params={"status": "merged"},
        headers=_auth(owner_token),
    ).json()
    assert fork["id"] in [d["id"] for d in merged_only]

    # A decided request cannot be decided again.
    again = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token)
    )
    assert again.status_code == 409


def test_accept_allowed_for_target_author(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, member_token, workspace_id, "Member's Doc")
    fork = _fork(client, owner_token, doc["id"])
    mr = _propose_merge(client, owner_token, fork["id"], doc["id"])
    # The target author (a plain member, not the workspace owner) may accept.
    accepted = client.post(
        f"/api/merge-requests/{mr['id']}/accept", headers=_auth(member_token)
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"


def test_reject_merge_request(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    member_token, _ = member
    doc = _create_document(client, owner_token, workspace_id, "Reject Me")
    fork = _fork(client, member_token, doc["id"])
    mr = _propose_merge(client, member_token, fork["id"], doc["id"])

    denied = client.post(
        f"/api/merge-requests/{mr['id']}/reject", headers=_auth(member_token)
    )
    assert denied.status_code == 403

    rejected = client.post(
        f"/api/merge-requests/{mr['id']}/reject", headers=_auth(owner_token)
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # The fork keeps its content and is NOT marked merged.
    fork_state = _workspace_doc(client, member_token, workspace_id, fork["id"])
    assert fork_state["status"] != "merged"

    for decide in ("accept", "reject"):
        response = client.post(
            f"/api/merge-requests/{mr['id']}/{decide}", headers=_auth(owner_token)
        )
        assert response.status_code == 409


def test_evolution_tree(
    client: TestClient,
    owner: tuple[str, int],
    member: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, owner_id = owner
    member_token, _ = member
    outsider_token, _ = outsider
    root = _create_document(client, owner_token, workspace_id, "Tree Root")
    fork_a = _fork(client, member_token, root["id"])
    fork_b = _fork(client, owner_token, fork_a["id"])
    # The same user may fork the same document only once per 30 minutes,
    # so the second fork of the root is made by the owner.
    fork_c = _fork(client, owner_token, root["id"])

    # The tree is the same no matter which node you start from.
    tree = client.get(f"/api/documents/{fork_b['id']}/tree", headers=_auth(member_token))
    assert tree.status_code == 200
    nodes = {node["id"]: node for node in tree.json()}
    assert set(nodes) == {root["id"], fork_a["id"], fork_b["id"], fork_c["id"]}
    assert nodes[root["id"]]["parent_id"] is None
    assert nodes[fork_a["id"]]["parent_id"] == root["id"]
    assert nodes[fork_b["id"]]["parent_id"] == fork_a["id"]
    assert nodes[fork_c["id"]]["parent_id"] == root["id"]
    assert nodes[root["id"]]["author"]["id"] == owner_id
    assert nodes[root["id"]]["author"]["display_name"] == "Evo Owner"
    assert all(not node["merged"] for node in nodes.values())
    assert all("vitality" in node and "status" in node for node in nodes.values())

    # Non-members cannot see the tree.
    denied = client.get(
        f"/api/documents/{root['id']}/tree", headers=_auth(outsider_token)
    )
    assert denied.status_code == 403

    # After a merge the merged fork is marked in the tree.
    mr = _propose_merge(client, member_token, fork_a["id"], root["id"])
    client.post(f"/api/merge-requests/{mr['id']}/accept", headers=_auth(owner_token))
    tree = client.get(f"/api/documents/{root['id']}/tree", headers=_auth(owner_token))
    nodes = {node["id"]: node for node in tree.json()}
    assert nodes[fork_a["id"]]["merged"] is True
    assert nodes[fork_a["id"]]["status"] == "merged"
    assert nodes[fork_b["id"]]["merged"] is False
