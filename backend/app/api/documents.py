"""Document CRUD routes, with vitality bookkeeping hooks.

Every view/edit charges the document's vitality through the M4 life
engine (throttled views, status refresh/revive); decay runs in the
background scheduler started in ``app.main``.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..life import record_interaction
from ..models import Attachment, Document, Interaction, Membership, User
from ..schemas import DocumentCreate, DocumentOut, DocumentUpdate
from .deps import get_current_user

router = APIRouter(tags=["documents"])


def require_membership(db: Session, workspace_id: int, user_id: int) -> Membership:
    """Return the user's membership or raise 403."""
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace"
        )
    return membership


def get_accessible_document(db: Session, document_id: int, user: User) -> Document:
    """Load a document, requiring workspace membership to see it."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    require_membership(db, document.workspace_id, user.id)
    return document


def document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        workspace_id=document.workspace_id,
        parent_id=document.parent_id,
        title=document.title,
        content_md=document.content_md,
        tags=json.loads(document.tags),
        author_id=document.author_id,
        vitality=document.vitality,
        status=document.status,
        last_interaction_at=document.last_interaction_at,
        created_at=document.created_at,
    )


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    workspace_id: int,
    payload: DocumentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    require_membership(db, workspace_id, user.id)
    document = Document(
        workspace_id=workspace_id,
        title=payload.title,
        content_md=payload.content_md,
        tags=json.dumps(payload.tags),
        author_id=user.id,
    )
    db.add(document)
    db.commit()
    return document_out(document)


@router.get(
    "/workspaces/{workspace_id}/documents", response_model=list[DocumentOut]
)
def list_documents(
    workspace_id: int,
    q: str | None = Query(default=None),
    doc_status: str | None = Query(default=None, alias="status"),
    parent: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    require_membership(db, workspace_id, user.id)
    stmt = select(Document).where(Document.workspace_id == workspace_id)
    if q:
        stmt = stmt.where(Document.title.like(f"%{q}%"))
    if doc_status:
        stmt = stmt.where(Document.status == doc_status)
    if parent == "null":
        # Trunk documents only (forked variants have a parent).
        stmt = stmt.where(Document.parent_id.is_(None))
    elif parent is not None and parent.isdigit():
        stmt = stmt.where(Document.parent_id == int(parent))
    stmt = stmt.order_by(Document.last_interaction_at.desc(), Document.id.desc())
    return [document_out(doc) for doc in db.scalars(stmt).all()]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = get_accessible_document(db, document_id, user)
    # Reading counts as a view: charge vitality and bump last_interaction_at.
    record_interaction(db, document, user.id, "view")
    db.commit()
    return document_out(document)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    # Any workspace member may edit (edit history/permissions arrive later).
    document = get_accessible_document(db, document_id, user)
    if payload.title is not None:
        document.title = payload.title
    if payload.content_md is not None:
        document.content_md = payload.content_md
    if payload.tags is not None:
        document.tags = json.dumps(payload.tags)
    record_interaction(db, document, user.id, "edit")
    db.commit()
    return document_out(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    document = get_accessible_document(db, document_id, user)
    membership = require_membership(db, document.workspace_id, user.id)
    if document.author_id != user.id and membership.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the author or the workspace owner can delete a document",
        )
    for model in (Interaction, Attachment):
        for row in db.scalars(
            select(model).where(model.document_id == document.id)
        ).all():
            db.delete(row)
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
