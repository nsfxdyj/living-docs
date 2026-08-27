"""Comment routes (M6): one-level, non-nested comments on documents.

Posting a comment charges the document's vitality (+5, see app.life) and
notifies the document's author (unless they commented themselves).
Comments can @mention workspace members by their exact display_name
(``@Jane Doe``); mentioned members get a ``mention`` notification. A
mentioned author receives only the mention notification, not a duplicate
comment notification. Mentions in document *edits* are intentionally not
notified (MVP: comments only).
"""

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..life import record_interaction
from ..models import Comment, Document, Membership, Notification, User
from ..notify import create_notification
from ..schemas import CommentCreate, CommentOut, UserOut
from .deps import get_current_user
from .documents import get_accessible_document, require_membership

router = APIRouter(tags=["comments"])

# Anti-flooding: the same (actor, target, document) mention produces at
# most one notification per window.
MENTION_THROTTLE = timedelta(minutes=10)


def find_mentioned_members(db: Session, workspace_id: int, body: str) -> list[User]:
    """Workspace members whose exact display_name appears as ``@name`` in body.

    Exact match with a leading non-word/non-@ boundary (so ``x@Jane`` in an
    email address does not count) and a trailing non-word boundary (so "Al"
    is not mentioned by "@Alice").

    Ambiguity rule (MVP tradeoff): if several members share the exact same
    display_name, a mention of that name notifies NOBODY rather than
    guessing or broadcasting. Duplicate names should be resolved socially.
    """
    members = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == workspace_id)
    ).all()
    by_name: dict[str, list[User]] = defaultdict(list)
    for member in members:
        by_name[member.display_name].append(member)
    mentioned: list[User] = []
    for name in sorted(by_name, key=len, reverse=True):
        if len(by_name[name]) != 1:
            continue  # ambiguous name: notify nobody
        pattern = r"(?<![\w@])@" + re.escape(name) + r"(?!\w)"
        if re.search(pattern, body):
            mentioned.append(by_name[name][0])
    return mentioned


def _mention_throttled(
    db: Session, *, target_id: int, actor_id: int, document_id: int
) -> bool:
    """True if this (actor, target, document) mention already fired recently."""
    cutoff = datetime.utcnow() - MENTION_THROTTLE
    recent = db.scalars(
        select(Notification).where(
            Notification.user_id == target_id,
            Notification.kind == "mention",
            Notification.created_at >= cutoff,
        )
    ).all()
    return any(
        (p := json.loads(n.payload)).get("actor_id") == actor_id
        and p.get("document_id") == document_id
        for n in recent
    )


def comment_out(comment: Comment, author: User) -> CommentOut:
    return CommentOut(
        id=comment.id,
        document_id=comment.document_id,
        author=UserOut(
            id=author.id, email=author.email, display_name=author.display_name
        ),
        body=comment.body,
        created_at=comment.created_at,
    )


@router.post(
    "/documents/{document_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    document_id: int,
    payload: CommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    document = get_accessible_document(db, document_id, user)
    comment = Comment(document_id=document.id, author_id=user.id, body=payload.body)
    db.add(comment)
    record_interaction(db, document, user.id, "comment")
    db.flush()  # assign comment.id for the notification payload
    mentioned = find_mentioned_members(db, document.workspace_id, payload.body)
    mentioned_ids: set[int] = set()
    for member in mentioned:
        if member.id == user.id:
            continue  # no self-notification
        # A mentioned author never gets a duplicate "comment" notification,
        # even when the mention itself is throttled away.
        mentioned_ids.add(member.id)
        if _mention_throttled(
            db, target_id=member.id, actor_id=user.id, document_id=document.id
        ):
            continue  # anti-flooding: one mention per (actor, target, doc, window)
        create_notification(
            db,
            user_id=member.id,
            workspace_id=document.workspace_id,
            kind="mention",
            payload={
                "document_id": document.id,
                "document_title": document.title,
                "comment_id": comment.id,
                "actor_id": user.id,
                "actor_name": user.display_name,
            },
        )
    if document.author_id != user.id and document.author_id not in mentioned_ids:
        create_notification(
            db,
            user_id=document.author_id,
            workspace_id=document.workspace_id,
            kind="comment",
            payload={
                "document_id": document.id,
                "document_title": document.title,
                "comment_id": comment.id,
                "actor_id": user.id,
                "actor_name": user.display_name,
            },
        )
    db.commit()
    return comment_out(comment, user)


@router.get(
    "/documents/{document_id}/comments", response_model=list[CommentOut]
)
def list_comments(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CommentOut]:
    get_accessible_document(db, document_id, user)
    comments = db.scalars(
        select(Comment)
        .where(Comment.document_id == document_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()
    authors = {
        author.id: author
        for author in db.scalars(
            select(User).where(User.id.in_({c.author_id for c in comments}))
        ).all()
    } if comments else {}
    return [comment_out(c, authors[c.author_id]) for c in comments]


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Comment not found")
    document = db.get(Document, comment.document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Comment not found")
    membership = require_membership(db, document.workspace_id, user.id)
    if comment.author_id != user.id and membership.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the comment author or the workspace owner can delete a comment",
        )
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
