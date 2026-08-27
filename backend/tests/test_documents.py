"""Tests for document CRUD, search, permissions and vitality hooks."""

import pytest
from fastapi.testclient import TestClient


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


def _create_workspace(client: TestClient, token: str, name: str) -> int:
    response = client.post("/api/workspaces", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_document(
    client: TestClient, token: str, workspace_id: int, title: str, **extra
) -> dict:
    payload = {"title": title, "content_md": "# hello", "tags": ["note"]}
    payload.update(extra)
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def owner_token(client: TestClient) -> str:
    return _register(client, "doc-owner@example.com", "Doc Owner")


@pytest.fixture(scope="module")
def member_token(client: TestClient) -> str:
    return _register(client, "doc-member@example.com", "Doc Member")


@pytest.fixture(scope="module")
def outsider_token(client: TestClient) -> str:
    return _register(client, "doc-outsider@example.com", "Doc Outsider")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner_token: str, member_token: str) -> int:
    wid = _create_workspace(client, owner_token, "Doc Team")
    invite = client.post(
        f"/api/workspaces/{wid}/invites", headers=_auth(owner_token)
    ).json()
    joined = client.post(
        "/api/workspaces/join",
        json={"token": invite["token"]},
        headers=_auth(member_token),
    )
    assert joined.status_code == 200, joined.text
    return wid


def test_create_document(client: TestClient, owner_token: str, workspace_id: int) -> None:
    doc = _create_document(
        client, owner_token, workspace_id, "Garden Guide", tags=["guide", "onboarding"]
    )
    assert doc["title"] == "Garden Guide"
    assert doc["tags"] == ["guide", "onboarding"]
    assert doc["workspace_id"] == workspace_id
    assert doc["parent_id"] is None
    assert doc["vitality"] == 0
    assert doc["status"] == "thriving"


def test_list_documents_sorted_by_last_interaction(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    _create_document(client, owner_token, workspace_id, "Watering Schedule")
    docs = client.get(
        f"/api/workspaces/{workspace_id}/documents", headers=_auth(owner_token)
    ).json()
    titles = [d["title"] for d in docs]
    assert "Garden Guide" in titles
    assert "Watering Schedule" in titles
    # Most recently interacted first.
    assert titles[0] == "Watering Schedule"


def test_search_by_title(client: TestClient, owner_token: str, workspace_id: int) -> None:
    docs = client.get(
        f"/api/workspaces/{workspace_id}/documents",
        params={"q": "garden"},
        headers=_auth(owner_token),
    ).json()
    assert [d["title"] for d in docs] == ["Garden Guide"]


def test_filter_by_status_and_parent(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    params = {"status": "thriving", "parent": "null"}
    docs = client.get(
        f"/api/workspaces/{workspace_id}/documents",
        params=params,
        headers=_auth(owner_token),
    ).json()
    assert len(docs) == 2
    assert all(d["status"] == "thriving" and d["parent_id"] is None for d in docs)
    empty = client.get(
        f"/api/workspaces/{workspace_id}/documents",
        params={"status": "withered"},
        headers=_auth(owner_token),
    ).json()
    assert empty == []


def test_view_records_interaction_and_charges_vitality(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Vitality Probe")
    viewed = client.get(f"/api/documents/{doc['id']}", headers=_auth(owner_token))
    assert viewed.status_code == 200
    data = viewed.json()
    assert data["vitality"] == 1  # view energy = 1
    assert data["last_interaction_at"] > doc["last_interaction_at"]


def test_member_can_edit_and_edit_charges_vitality(
    client: TestClient, owner_token: str, member_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Shared Draft")
    response = client.patch(
        f"/api/documents/{doc['id']}",
        json={"content_md": "edited by member", "tags": ["draft"]},
        headers=_auth(member_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["content_md"] == "edited by member"
    assert data["tags"] == ["draft"]
    assert data["title"] == "Shared Draft"  # untouched field preserved
    assert data["vitality"] == 8  # edit energy = 8


def test_delete_requires_author_or_owner(
    client: TestClient, owner_token: str, member_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Doomed Doc")

    # A member who is neither author nor owner cannot delete.
    denied = client.delete(
        f"/api/documents/{doc['id']}", headers=_auth(member_token)
    )
    assert denied.status_code == 403

    # The workspace owner can delete someone else's document.
    deleted = client.delete(
        f"/api/documents/{doc['id']}", headers=_auth(owner_token)
    )
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/documents/{doc['id']}", headers=_auth(owner_token)).status_code
        == 404
    )

    # The author can delete their own document.
    own = _create_document(client, member_token, workspace_id, "Member's Own")
    assert (
        client.delete(
            f"/api/documents/{own['id']}", headers=_auth(member_token)
        ).status_code
        == 204
    )


def test_non_member_forbidden_everywhere(
    client: TestClient, owner_token: str, outsider_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Private Doc")
    endpoints = [
        client.get(
            f"/api/workspaces/{workspace_id}/documents", headers=_auth(outsider_token)
        ),
        client.post(
            f"/api/workspaces/{workspace_id}/documents",
            json={"title": "x"},
            headers=_auth(outsider_token),
        ),
        client.get(f"/api/documents/{doc['id']}", headers=_auth(outsider_token)),
        client.patch(
            f"/api/documents/{doc['id']}",
            json={"title": "y"},
            headers=_auth(outsider_token),
        ),
        client.delete(f"/api/documents/{doc['id']}", headers=_auth(outsider_token)),
    ]
    assert [r.status_code for r in endpoints] == [403] * 5


def test_document_routes_require_auth(client: TestClient, workspace_id: int) -> None:
    assert client.get(f"/api/workspaces/{workspace_id}/documents").status_code == 401
    assert (
        client.post(
            f"/api/workspaces/{workspace_id}/documents", json={"title": "x"}
        ).status_code
        == 401
    )
    assert client.get("/api/documents/1").status_code == 401
    assert client.patch("/api/documents/1", json={"title": "x"}).status_code == 401
    assert client.delete("/api/documents/1").status_code == 401
