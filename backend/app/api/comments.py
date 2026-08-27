"""Comment routes (M6): one-level, non-nested comments on documents.

Posting a comment charges the document's vitality (+5, see app.life) and
notifies the document's author (unless they commented themselves).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..life import record_interaction
from ..models import Comment, Document, User
from ..notify import create_notification
from ..schemas import CommentCreate, CommentOut, UserOut
from .deps import get_current_user
from .documents import get_accessible_document, require_membership

router = APIRouter(tags=["comments"])


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
    if document.author_id != user.id:
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
