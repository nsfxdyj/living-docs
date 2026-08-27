"""Tests for FTS5 full-text search: hits, snippets, sync, rebuild, access."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from app.search import (
    SNIPPET_CLOSE,
    SNIPPET_OPEN,
    ensure_fts_table,
    rebuild_index_if_stale,
)


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
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        json={"title": title, "content_md": content_md},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _search(client: TestClient, token: str, wid: int, q: str) -> list[dict]:
    response = client.get(
        f"/api/workspaces/{wid}/search", params={"q": q}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def owner(client: TestClient) -> tuple[str, int]:
    return _register(client, "search-owner@example.com", "Search Owner")


@pytest.fixture(scope="module")
def outsider(client: TestClient) -> tuple[str, int]:
    return _register(client, "search-outsider@example.com", "Search Outsider")


@pytest.fixture(scope="module")
def workspace_id(client: TestClient, owner: tuple[str, int]) -> int:
    return _create_workspace(client, owner[0], "Search Team")


def test_search_hits_title_and_content(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    title_doc = _create_document(
        client, token, workspace_id, "Photosynthesis Guide", "just some text"
    )
    body_doc = _create_document(
        client,
        token,
        workspace_id,
        "Unrelated Title",
        "Deep dive into photosynthesis mechanisms.",
    )

    hits = _search(client, token, workspace_id, "photosynthesis")
    hit_ids = {hit["id"] for hit in hits}
    assert {title_doc["id"], body_doc["id"]} <= hit_ids
    for hit in hits:
        assert set(hit) == {"id", "title", "snippet", "vitality", "status", "rank"}
        assert hit["status"] != "merged"


def test_snippet_highlights_match(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    _create_document(
        client,
        token,
        workspace_id,
        "Snippet Doc",
        "The mitochondria is the powerhouse of the cell.",
    )
    hits = _search(client, token, workspace_id, "mitochondria")
    assert len(hits) == 1
    # Snippet highlight markers are control characters, never literal <b>
    # (so document text cannot forge a highlight).
    marker = f"{SNIPPET_OPEN}mitochondria{SNIPPET_CLOSE}"
    assert marker in hits[0]["snippet"]
    assert "<b>" not in hits[0]["snippet"]


def test_search_reflects_updates_and_deletes(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    doc = _create_document(
        client, token, workspace_id, "Mutable Doc", "contains zephyr initially"
    )
    assert any(h["id"] == doc["id"] for h in _search(client, token, workspace_id, "zephyr"))

    updated = client.patch(
        f"/api/documents/{doc['id']}",
        json={"content_md": "the term was removed"},
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text
    assert not any(h["id"] == doc["id"] for h in _search(client, token, workspace_id, "zephyr"))

    # A rename is indexed too.
    renamed = client.patch(
        f"/api/documents/{doc['id']}",
        json={"title": "Zephyr Returns"},
        headers=_auth(token),
    )
    assert renamed.status_code == 200, renamed.text
    assert any(h["id"] == doc["id"] for h in _search(client, token, workspace_id, "zephyr"))

    deleted = client.delete(f"/api/documents/{doc['id']}", headers=_auth(token))
    assert deleted.status_code == 204
    assert not any(h["id"] == doc["id"] for h in _search(client, token, workspace_id, "zephyr"))


def test_merged_documents_excluded(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    trunk = _create_document(
        client, token, workspace_id, "Trunk Doc", "trunk content"
    )
    fork = client.post(
        f"/api/documents/{trunk['id']}/fork", headers=_auth(token)
    )
    assert fork.status_code == 201, fork.text
    fork_doc = fork.json()
    updated = client.patch(
        f"/api/documents/{fork_doc['id']}",
        json={"content_md": "uniquely quixotic fork content"},
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text

    assert any(
        h["id"] == fork_doc["id"]
        for h in _search(client, token, workspace_id, "quixotic")
    )

    mr = client.post(
        f"/api/documents/{fork_doc['id']}/merge-requests",
        json={"target_doc_id": trunk["id"]},
        headers=_auth(token),
    )
    assert mr.status_code == 201, mr.text
    accepted = client.post(
        f"/api/merge-requests/{mr.json()['id']}/accept", headers=_auth(token)
    )
    assert accepted.status_code == 200, accepted.text

    # The merged fork no longer appears; its content moved to the trunk.
    hits = _search(client, token, workspace_id, "quixotic")
    assert [h["id"] for h in hits] == [trunk["id"]]


def test_search_access_control(
    client: TestClient,
    owner: tuple[str, int],
    outsider: tuple[str, int],
    workspace_id: int,
) -> None:
    owner_token, _ = owner
    outsider_token, _ = outsider
    _create_document(client, owner_token, workspace_id, "Guarded Search Doc")

    assert (
        client.get(
            f"/api/workspaces/{workspace_id}/search", params={"q": "guarded"}
        ).status_code
        == 401
    )
    denied = client.get(
        f"/api/workspaces/{workspace_id}/search",
        params={"q": "guarded"},
        headers=_auth(outsider_token),
    )
    assert denied.status_code == 403


def test_cjk_substring_search(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    """Regression: the trigram tokenizer must find CJK substrings.

    unicode61 (the previous tokenizer) indexed a whole run of Chinese
    characters as ONE token, so "光合" never matched "光合作用".
    """
    token, _ = owner
    doc = _create_document(
        client, token, workspace_id, "植物笔记", "光合作用是生命之源。"
    )
    # >=3 characters: served by the trigram FTS index.
    hits = _search(client, token, workspace_id, "光合作")
    assert [h["id"] for h in hits] == [doc["id"]]
    assert SNIPPET_OPEN in hits[0]["snippet"]
    # <3 characters: trigram cannot serve this; LIKE fallback must hit.
    hits = _search(client, token, workspace_id, "光合")
    assert [h["id"] for h in hits] == [doc["id"]]


def test_search_query_too_long(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    response = client.get(
        f"/api/workspaces/{workspace_id}/search",
        params={"q": "x" * 201},
        headers=_auth(token),
    )
    assert response.status_code == 422
    ok = client.get(
        f"/api/workspaces/{workspace_id}/search",
        params={"q": "x" * 200},
        headers=_auth(token),
    )
    assert ok.status_code == 200


def test_search_query_edge_cases(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    _create_document(client, token, workspace_id, "Edge Case Doc", 'he said "hi"')

    # Empty / whitespace / tokenless queries return no results, not an error.
    assert _search(client, token, workspace_id, "") == []
    assert _search(client, token, workspace_id, "   ") == []
    assert _search(client, token, workspace_id, "!@#$%^&*()") == []

    # FTS5 metacharacters in user input must not break the MATCH query.
    for nasty in (
        '"; DROP TABLE documents; --',
        "foo OR bar NEAR baz",
        "title: hello",
        "a* b(c)",
        '"""',
    ):
        response = client.get(
            f"/api/workspaces/{workspace_id}/search",
            params={"q": nasty},
            headers=_auth(token),
        )
        assert response.status_code == 200, (nasty, response.text)


def test_rebuild_index_recovers_legacy_rows(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    token, _ = owner
    doc = _create_document(
        client, token, workspace_id, "Legacy Doc", "written before the index"
    )

    # Simulate pre-FTS data: index rows are missing entirely.
    with SessionLocal() as session:
        session.execute(text("DELETE FROM document_fts"))
        session.commit()
    assert _search(client, token, workspace_id, "legacy") == []

    with SessionLocal() as session:
        assert rebuild_index_if_stale(session) is True
    hits = _search(client, token, workspace_id, "legacy")
    assert [h["id"] for h in hits] == [doc["id"]]

    # A consistent index is left alone.
    with SessionLocal() as session:
        assert rebuild_index_if_stale(session) is False


def test_rebuild_detects_same_count_drift(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    """Row counts alone cannot detect drift; the set difference can."""
    token, _ = owner
    doc = _create_document(
        client, token, workspace_id, "Drifted Doc", "drift detection content"
    )
    with SessionLocal() as session:
        # Same row count, wrong row ids: swap the real row for a bogus one.
        session.execute(
            text("DELETE FROM document_fts WHERE rowid = :doc_id"),
            {"doc_id": doc["id"]},
        )
        session.execute(
            text("INSERT INTO document_fts(rowid, title, content_md) "
                 "VALUES (999999, 'bogus', 'bogus')")
        )
        session.commit()
        assert rebuild_index_if_stale(session) is True

    hits = _search(client, token, workspace_id, "drift")
    assert [h["id"] for h in hits] == [doc["id"]]


def test_ensure_recreates_table_after_tokenizer_change(
    client: TestClient, owner: tuple[str, int], workspace_id: int
) -> None:
    """An FTS table created with the old unicode61 tokenizer is rebuilt."""
    token, _ = owner
    doc = _create_document(
        client, token, workspace_id, "Tokenizer Doc", "旧分词器时代的文档内容"
    )
    with SessionLocal() as session:
        session.execute(text("DROP TABLE document_fts"))
        session.execute(
            text("CREATE VIRTUAL TABLE document_fts USING fts5(title, content_md)")
        )
        session.execute(
            text("INSERT INTO document_fts(rowid, title, content_md) "
                 "VALUES (:doc_id, 'stale', 'stale')"),
            {"doc_id": doc["id"]},
        )
        session.commit()

        ensure_fts_table(session)  # must drop the unicode61 table
        sql = session.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'document_fts'")
        ).scalar()
        assert "trigram" in sql

        # The table was recreated empty, so the set difference triggers a
        # rebuild that repopulates it from the documents table.
        assert rebuild_index_if_stale(session) is True

    hits = _search(client, token, workspace_id, "分词器")
    assert [h["id"] for h in hits] == [doc["id"]]
