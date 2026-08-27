"""Tests for the auth routes: register, login, /me."""

from fastapi.testclient import TestClient


def test_register_first_user_creates_default_workspace(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "password123",
            "display_name": "Alice",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["token"]
    assert data["user"] == {"id": 1, "email": "alice@example.com", "display_name": "Alice"}

    # The first registered user automatically owns a default workspace.
    workspaces = client.get(
        "/api/workspaces", headers={"Authorization": f"Bearer {data['token']}"}
    )
    assert workspaces.status_code == 200
    body = workspaces.json()
    assert len(body) == 1
    assert body[0]["name"] == "Alice's Workspace"
    assert body[0]["role"] == "owner"


def test_register_duplicate_email_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "password123",
            "display_name": "Alice Again",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}


def test_register_short_password_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "shorty@example.com",
            "password": "short",
            "display_name": "Shorty",
        },
    )
    assert response.status_code == 422


def test_login_success(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"]
    assert data["user"]["email"] == "alice@example.com"


def test_login_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_login_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_me_with_valid_token(client: TestClient) -> None:
    token = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    ).json()["token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_me_without_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_me_with_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
