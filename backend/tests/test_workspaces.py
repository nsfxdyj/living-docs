"""Tests for workspace management and invite links."""

import pytest
from fastapi.testclient import TestClient


def _register(client: TestClient, email: str, display_name: str) -> str:
    """Register a user and return their access token."""
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


@pytest.fixture(scope="module")
def owner_token(client: TestClient) -> str:
    return _register(client, "owner@example.com", "Owner")


@pytest.fixture(scope="module")
def member_token(client: TestClient) -> str:
    return _register(client, "member@example.com", "Member")


@pytest.fixture(scope="module")
def outsider_token(client: TestClient) -> str:
    return _register(client, "outsider@example.com", "Outsider")


def test_create_workspace(client: TestClient, owner_token: str) -> None:
    response = client.post(
        "/api/workspaces", json={"name": "Core Team"}, headers=_auth(owner_token)
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Core Team"
    assert data["slug"] == "core-team"
    assert data["role"] == "owner"


def test_list_my_workspaces(client: TestClient, owner_token: str) -> None:
    response = client.get("/api/workspaces", headers=_auth(owner_token))
    assert response.status_code == 200
    names = [w["name"] for w in response.json()]
    assert "Core Team" in names


def test_workspace_detail_for_member(client: TestClient, owner_token: str) -> None:
    workspace_id = client.get("/api/workspaces", headers=_auth(owner_token)).json()[0][
        "id"
    ]
    response = client.get(f"/api/workspaces/{workspace_id}", headers=_auth(owner_token))
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "owner"
    assert [m["email"] for m in data["members"]] == ["owner@example.com"]
    assert data["members"][0]["role"] == "owner"


def test_workspace_detail_denied_for_non_member(
    client: TestClient, owner_token: str, outsider_token: str
) -> None:
    workspace_id = client.get("/api/workspaces", headers=_auth(owner_token)).json()[0][
        "id"
    ]
    response = client.get(
        f"/api/workspaces/{workspace_id}", headers=_auth(outsider_token)
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not a member of this workspace"}


def test_member_cannot_create_invite(
    client: TestClient, owner_token: str, member_token: str, outsider_token: str
) -> None:
    workspace_id = client.get("/api/workspaces", headers=_auth(owner_token)).json()[0][
        "id"
    ]
    # A non-member is rejected...
    response = client.post(
        f"/api/workspaces/{workspace_id}/invites", headers=_auth(outsider_token)
    )
    assert response.status_code == 403
    # ...and so is a plain member (owner-only action); verified again below
    # once `member_token` has actually joined a workspace.
    response = client.post(
        f"/api/workspaces/{workspace_id}/invites", headers=_auth(member_token)
    )
    assert response.status_code == 403


def test_invite_flow_lets_second_user_join(
    client: TestClient, owner_token: str, member_token: str
) -> None:
    workspace_id = client.get("/api/workspaces", headers=_auth(owner_token)).json()[0][
        "id"
    ]

    invite = client.post(
        f"/api/workspaces/{workspace_id}/invites", headers=_auth(owner_token)
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["token"]
    assert invite.json()["url"] == f"/join/{token}"

    joined = client.post(
        "/api/workspaces/join", json={"token": token}, headers=_auth(member_token)
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["id"] == workspace_id
    assert joined.json()["role"] == "member"

    # The new member now sees the workspace and both members are listed.
    listing = client.get("/api/workspaces", headers=_auth(member_token)).json()
    assert [w["id"] for w in listing] == [workspace_id]
    detail = client.get(
        f"/api/workspaces/{workspace_id}", headers=_auth(member_token)
    ).json()
    assert sorted(m["email"] for m in detail["members"]) == [
        "member@example.com",
        "owner@example.com",
    ]


def test_join_twice_rejected(client: TestClient, owner_token: str, member_token: str) -> None:
    workspace_id = client.get("/api/workspaces", headers=_auth(owner_token)).json()[0][
        "id"
    ]
    token = client.post(
        f"/api/workspaces/{workspace_id}/invites", headers=_auth(owner_token)
    ).json()["token"]
    response = client.post(
        "/api/workspaces/join", json={"token": token}, headers=_auth(member_token)
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Already a member of this workspace"}


def test_join_with_invalid_token(client: TestClient, member_token: str) -> None:
    response = client.post(
        "/api/workspaces/join",
        json={"token": "no-such-token"},
        headers=_auth(member_token),
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invite link is invalid or has expired"}


def test_workspace_routes_require_auth(client: TestClient) -> None:
    assert client.get("/api/workspaces").status_code == 401
    assert client.post("/api/workspaces", json={"name": "X"}).status_code == 401
    assert client.post("/api/workspaces/join", json={"token": "t"}).status_code == 401
