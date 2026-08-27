"""Tests for the M4 life engine: thresholds, decay, revive, view throttle, garden."""

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.life import refresh_status, run_decay, status_for_vitality
from app.models import Document


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


def _join_workspace(client: TestClient, owner_token: str, token: str, wid: int) -> None:
    invite = client.post(
        f"/api/workspaces/{wid}/invites", headers=_auth(owner_token)
    ).json()
    joined = client.post(
        "/api/workspaces/join", json={"token": invite["token"]}, headers=_auth(token)
    )
    assert joined.status_code == 200, joined.text


def _create_document(
    client: TestClient, token: str, workspace_id: int, title: str, **extra
) -> dict:
    payload = {"title": title, "content_md": "# hello", "tags": ["life"]}
    payload.update(extra)
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edit(client: TestClient, token: str, document_id: int, content: str) -> dict:
    response = client.patch(
        f"/api/documents/{document_id}",
        json={"content_md": content},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _set_vitality(document_id: int, vitality: float) -> None:
    """Directly set a document's vitality/status (time travel for tests)."""
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.vitality = vitality
        refresh_status(document)
        session.commit()


def _get_document(document_id: int) -> Document:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        session.expunge(document)
        return document


@pytest.fixture(scope="module")
def owner_token(client: TestClient) -> str:
    return _register(client, "life-owner@example.com", "Life Owner")


@pytest.fixture(scope="module")
def member_token(client: TestClient) -> str:
    return _register(client, "life-member@example.com", "Life Member")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner_token: str, member_token: str) -> int:
    wid = _create_workspace(client, owner_token, "Life Lab")
    _join_workspace(client, owner_token, member_token, wid)
    return wid


def test_status_threshold_boundaries() -> None:
    assert status_for_vitality(60.0) == "thriving"
    assert status_for_vitality(59.9) == "stable"
    assert status_for_vitality(30.0) == "stable"
    assert status_for_vitality(29.9) == "fading"
    assert status_for_vitality(10.0) == "fading"
    assert status_for_vitality(9.9) == "withered"
    assert status_for_vitality(0.0) == "withered"


def test_decay_tick_reduces_vitality_and_updates_status(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Decay Probe")
    for i in range(8):
        data = _edit(client, owner_token, doc["id"], f"edit {i}")
    assert data["vitality"] == 64
    assert data["status"] == "thriving"

    with SessionLocal() as session:
        assert run_decay(session) >= 1
    document = _get_document(doc["id"])
    assert document.vitality == pytest.approx(64 * 0.95)
    assert document.status == "thriving"  # 60.8 still >= 60

    with SessionLocal() as session:
        run_decay(session)
    document = _get_document(doc["id"])
    assert document.vitality == pytest.approx(64 * 0.95**2)
    assert document.status == "stable"  # 57.76 dropped below 60


def test_withered_document_revives_on_edit(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Forgotten Page")
    _set_vitality(doc["id"], 5.0)
    assert _get_document(doc["id"]).status == "withered"

    data = _edit(client, owner_token, doc["id"], "back from the dead")
    assert data["vitality"] == pytest.approx(5.0 + 8)
    assert data["status"] == "fading"  # 13 >= 10: revived out of withered


def test_repeat_view_within_throttle_window_does_not_recharge(
    client: TestClient, owner_token: str, member_token: str, workspace_id: int
) -> None:
    doc = _create_document(client, owner_token, workspace_id, "Throttle Probe")

    first = client.get(f"/api/documents/{doc['id']}", headers=_auth(owner_token))
    assert first.json()["vitality"] == 1

    # Same user, immediately again: throttled, no extra energy.
    second = client.get(f"/api/documents/{doc['id']}", headers=_auth(owner_token))
    assert second.json()["vitality"] == 1

    # A different user viewing is a fresh interaction and charges normally.
    other = client.get(f"/api/documents/{doc['id']}", headers=_auth(member_token))
    assert other.json()["vitality"] == 2


def test_garden_returns_trunk_documents_sorted_by_vitality(
    client: TestClient, owner_token: str, workspace_id: int
) -> None:
    high = _create_document(
        client, owner_token, workspace_id, "High Vital", tags=["hot"]
    )
    mid = _create_document(client, owner_token, workspace_id, "Mid Vital")
    low = _create_document(client, owner_token, workspace_id, "Low Vital")
    _set_vitality(high["id"], 80.0)
    _set_vitality(mid["id"], 40.0)
    _set_vitality(low["id"], 5.0)

    # A forked variant (parent_id set) must not appear in the garden.
    with SessionLocal() as session:
        fork = Document(
            workspace_id=workspace_id,
            parent_id=high["id"],
            title="High Vital (fork)",
            author_id=_get_document(high["id"]).author_id,
            vitality=999.0,
            status="thriving",
        )
        session.add(fork)
        session.commit()

    response = client.get(
        f"/api/workspaces/{workspace_id}/garden", headers=_auth(owner_token)
    )
    assert response.status_code == 200, response.text
    garden = response.json()
    by_title = {entry["title"]: entry for entry in garden}
    assert "High Vital (fork)" not in by_title

    probe = [by_title[t] for t in ("High Vital", "Mid Vital", "Low Vital")]
    positions = [garden.index(entry) for entry in probe]
    assert positions == sorted(positions)  # descending vitality order

    entry = by_title["High Vital"]
    assert entry["vitality"] == pytest.approx(80.0)
    assert entry["status"] == "thriving"
    assert entry["tags"] == ["hot"]
    assert entry["author"]["display_name"] == "Life Owner"
    assert entry["last_interaction_at"]
    assert set(entry) == {
        "id",
        "title",
        "vitality",
        "status",
        "tags",
        "last_interaction_at",
        "author",
    }


def test_garden_requires_membership(
    client: TestClient, workspace_id: int
) -> None:
    outsider = _register(client, "life-outsider@example.com", "Outsider")
    response = client.get(
        f"/api/workspaces/{workspace_id}/garden", headers=_auth(outsider)
    )
    assert response.status_code == 403
    assert (
        client.get(f"/api/workspaces/{workspace_id}/garden").status_code == 401
    )
