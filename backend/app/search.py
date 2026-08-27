"""Full-text search over documents using SQLite FTS5 (trigram tokenizer).

A ``document_fts`` virtual table mirrors ``documents(title, content_md)``
with ``rowid == documents.id``. The trigram tokenizer matches arbitrary
>=3-character substrings, which is what makes CJK search work (unicode61
treats a whole run of Chinese characters as one token). Queries whose
tokens are all shorter than 3 characters fall back to a plain ``LIKE``
scan, since trigram cannot index them.

The index is kept in sync inside the same transaction as every document
create/update/delete (see api/documents.py and api/evolution.py);
``rebuild_index_if_stale`` runs at startup to catch up documents written
before the FTS table existed or after a tokenizer change (no Alembic yet,
so the table is created with CREATE VIRTUAL TABLE IF NOT EXISTS).

Snippet highlight markers are the control characters \\x00 / \\x01 (not
``<b>``), so literal ``<b>`` text in a document can never forge a
highlight; the client escapes HTML and maps the markers to ``<b>`` tags.

FTS5 is probed once at startup: if the build lacks it, search returns 503
and document writes degrade to a logged warning instead of failing.
"""

import logging
import re

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from .models import Document

logger = logging.getLogger(__name__)

FTS_TABLE = "document_fts"
FTS_TOKENIZER = "trigram"

SEARCH_LIMIT = 50

# Trigram indexes substrings of at least this many characters; shorter
# query tokens must use the LIKE fallback.
TRIGRAM_MIN_TOKEN = 3

# Snippet highlight markers (control characters; \x00 is unusable
# because FTS5 snippet() truncates marker strings at a NUL byte).
SNIPPET_OPEN = "\x01"
SNIPPET_CLOSE = "\x02"

# Word characters (Unicode-aware: also matches CJK ideographs). Everything
# else in a user query is dropped before building the MATCH/LIKE query.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Probed once at startup via probe_fts5().
_FTS_AVAILABLE = True


def probe_fts5(db: Session) -> bool:
    """Check FTS5 support once at startup; remember the result."""
    global _FTS_AVAILABLE
    try:
        db.execute(text("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x)"))
        db.execute(text("DROP TABLE temp.fts5_probe"))
        db.commit()
        _FTS_AVAILABLE = True
    except Exception:  # noqa: BLE001 - any failure means "no FTS5"
        db.rollback()
        _FTS_AVAILABLE = False
        logger.warning(
            "SQLite FTS5 is not available; full-text search is disabled "
            "(search returns 503, document writes skip indexing)"
        )
    return _FTS_AVAILABLE


def fts_available() -> bool:
    return _FTS_AVAILABLE


def _fts_table_sql(db: Session) -> str | None:
    """The CREATE statement of the FTS table, or None if it does not exist."""
    row = db.execute(
        text("SELECT sql FROM sqlite_master WHERE name = :name"),
        {"name": FTS_TABLE},
    ).scalar()
    return row


def ensure_fts_table(db: Session) -> None:
    """Create the FTS5 table; drop and recreate it on a tokenizer change."""
    if not _FTS_AVAILABLE:
        return
    existing = _fts_table_sql(db)
    if existing is not None and FTS_TOKENIZER not in existing:
        # Created by an older version with a different tokenizer: rebuild.
        db.execute(text(f"DROP TABLE {FTS_TABLE}"))
        existing = None
    if existing is None:
        db.execute(
            text(
                f"CREATE VIRTUAL TABLE {FTS_TABLE} "
                f"USING fts5(title, content_md, tokenize='{FTS_TOKENIZER}')"
            )
        )


def _indexable(text_value: str) -> str:
    """Strip snippet marker control characters so they cannot be forged."""
    return text_value.replace(SNIPPET_OPEN, "").replace(SNIPPET_CLOSE, "")


def index_document(db: Session, document: Document) -> None:
    """Insert or replace a document's FTS row (same transaction as the write).

    Indexing failures (e.g. FTS5 unavailable) degrade to a warning: the
    document write itself must never fail because of the search index.
    """
    if not _FTS_AVAILABLE:
        return
    try:
        ensure_fts_table(db)
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid = :doc_id"),
            {"doc_id": document.id},
        )
        db.execute(
            text(f"INSERT INTO {FTS_TABLE}(rowid, title, content_md) "
                 "VALUES (:doc_id, :title, :content_md)"),
            {
                "doc_id": document.id,
                "title": _indexable(document.title),
                "content_md": _indexable(document.content_md),
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to index document %s for search", document.id, exc_info=True
        )


def remove_document(db: Session, document_id: int) -> None:
    """Drop a document's FTS row (degrades to a warning like index_document)."""
    if not _FTS_AVAILABLE:
        return
    try:
        ensure_fts_table(db)
        db.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid = :doc_id"),
            {"doc_id": document_id},
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to remove document %s from the search index",
            document_id,
            exc_info=True,
        )


def _index_drifted(db: Session) -> bool:
    """True if the FTS row ids differ from the documents ids (set difference)."""
    missing = db.execute(
        text(
            f"SELECT id FROM documents EXCEPT SELECT rowid FROM {FTS_TABLE} LIMIT 1"
        )
    ).first()
    if missing is not None:
        return True
    stale = db.execute(
        text(
            f"SELECT rowid FROM {FTS_TABLE} EXCEPT SELECT id FROM documents LIMIT 1"
        )
    ).first()
    return stale is not None


def rebuild_index_if_stale(db: Session) -> bool:
    """Rebuild the FTS index when its rows disagree with ``documents``.

    Set-difference check in both directions (a bare row count cannot detect
    same-count drift). Runs at startup to catch up pre-FTS legacy data and
    tokenizer changes; the index is transactional with document writes from
    then on.
    """
    if not _FTS_AVAILABLE:
        return False
    ensure_fts_table(db)
    if not _index_drifted(db):
        return False
    db.execute(text(f"DELETE FROM {FTS_TABLE}"))
    for document in db.scalars(select(Document)).all():
        index_document(db, document)
    db.commit()
    return True


def build_match_query(q: str) -> str | None:
    """Turn free-text user input into a safe FTS5 MATCH string.

    Only word tokens survive; each is double-quoted (embedded quotes
    doubled), so MATCH metacharacters (``"``, ``*``, ``OR``/``NEAR`` …) can
    never be injected. Tokens are OR-ed so any term can hit.
    """
    tokens = _TOKEN_RE.findall(q)
    if not tokens:
        return None
    return " OR ".join('"{}"'.format(t.replace('"', '""')) for t in tokens)


def _like_escape(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_documents(db: Session, workspace_id: int, q: str) -> list[dict]:
    """Search one workspace; merged documents are excluded.

    Returns rows of {id, title, snippet, vitality, status, rank} ordered by
    relevance, capped at SEARCH_LIMIT. An empty or tokenless query returns
    no results. Queries with only short (<3 char) tokens use a LIKE scan
    (the trigram index cannot serve them).
    """
    tokens = _TOKEN_RE.findall(q)
    if not tokens:
        return []
    ensure_fts_table(db)

    if all(len(t) >= TRIGRAM_MIN_TOKEN for t in tokens):
        match = build_match_query(q)
        rows = db.execute(
            text(
                f"SELECT d.id AS id, d.title AS title, "
                f"snippet({FTS_TABLE}, -1, :open, :close, '…', 24) AS snippet, "
                f"d.vitality AS vitality, d.status AS status, "
                f"bm25({FTS_TABLE}) AS rank "
                f"FROM {FTS_TABLE} "
                f"JOIN documents d ON d.id = {FTS_TABLE}.rowid "
                f"WHERE {FTS_TABLE} MATCH :match "
                f"AND d.workspace_id = :workspace_id "
                f"AND d.status != 'merged' "
                f"ORDER BY rank "
                f"LIMIT {SEARCH_LIMIT}"
            ),
            {
                "match": match,
                "open": SNIPPET_OPEN,
                "close": SNIPPET_CLOSE,
                "workspace_id": workspace_id,
            },
        ).all()
        return [
            {
                "id": row.id,
                "title": row.title,
                "snippet": row.snippet,
                "vitality": row.vitality,
                "status": row.status,
                "rank": row.rank,
            }
            for row in rows
        ]

    # LIKE fallback for short tokens (e.g. two-character CJK words).
    conditions = or_(
        *(
            or_(
                Document.title.like(f"%{_like_escape(t)}%", escape="\\"),
                Document.content_md.like(f"%{_like_escape(t)}%", escape="\\"),
            )
            for t in tokens
        )
    )
    docs = db.scalars(
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.status != "merged",
            conditions,
        )
        .order_by(Document.last_interaction_at.desc(), Document.id.desc())
        .limit(SEARCH_LIMIT)
    ).all()
    return [
        {
            "id": doc.id,
            "title": doc.title,
            # No FTS snippet in fallback mode; the client highlights nothing.
            "snippet": "",
            "vitality": doc.vitality,
            "status": doc.status,
            "rank": 0.0,
        }
        for doc in docs
    ]
