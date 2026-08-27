"""Workspace routes: creation, listing, details, invite links and joining."""

import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, Invite, Membership, User, Workspace
from ..schemas import (
    GardenEntry,
    InviteOut,
    JoinRequest,
    MemberOut,
    UserOut,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceOut,
)
from ..security import new_invite_token
from .deps import get_current_user

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

INVITE_EXPIRE_DAYS = 7


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "workspace"


def unique_slug(db: Session, name: str) -> str:
    """Derive a URL-safe slug from the name, suffixed until unique."""
    base = _slugify(name)
    slug = base
    counter = 2
    while db.scalar(select(Workspace).where(Workspace.slug == slug)) is not None:
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _workspace_out(workspace: Workspace, role: str | None = None) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.owner_id,
        role=role,
    )


def _get_membership(db: Session, workspace_id: int, user_id: int) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    workspace = Workspace(
        name=payload.name,
        slug=unique_slug(db, payload.name),
        owner_id=user.id,
    )
    db.add(workspace)
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=workspace.id, role="owner"))
    db.commit()
    return _workspace_out(workspace, role="owner")


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceOut]:
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.id)
    ).all()
    return [_workspace_out(workspace, role=role) for workspace, role in rows]


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceDetail:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    membership = _get_membership(db, workspace_id, user.id)
    if membership is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace"
        )
    rows = db.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(User.id)
    ).all()
    return WorkspaceDetail(
        **_workspace_out(workspace, role=membership.role).model_dump(),
        members=[
            MemberOut(
                user_id=member.id,
                email=member.email,
                display_name=member.display_name,
                role=role,
            )
            for member, role in rows
        ],
    )


@router.get("/{workspace_id}/garden", response_model=list[GardenEntry])
def get_garden(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GardenEntry]:
    """Garden data: all trunk documents, most alive first (M4)."""
    if _get_membership(db, workspace_id, user.id) is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace"
        )
    rows = db.execute(
        select(Document, User)
        .join(User, User.id == Document.author_id)
        .where(Document.workspace_id == workspace_id, Document.parent_id.is_(None))
        .order_by(Document.vitality.desc(), Document.id)
    ).all()
    return [
        GardenEntry(
            id=document.id,
            title=document.title,
            vitality=document.vitality,
            status=document.status,
            tags=json.loads(document.tags),
            last_interaction_at=document.last_interaction_at,
            author=UserOut(
                id=author.id, email=author.email, display_name=author.display_name
            ),
        )
        for document, author in rows
    ]


@router.post(
    "/{workspace_id}/invites",
    response_model=InviteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteOut:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    membership = _get_membership(db, workspace_id, user.id)
    if membership is None or membership.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner can create invites",
        )
    invite = Invite(
        workspace_id=workspace_id,
        token=new_invite_token(),
        created_by_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=INVITE_EXPIRE_DAYS),
    )
    db.add(invite)
    db.commit()
    return InviteOut(
        token=invite.token,
        url=f"/join/{invite.token}",
        expires_at=invite.expires_at,
    )


@router.post("/join", response_model=WorkspaceOut)
def join_workspace(
    payload: JoinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    invite = db.scalar(select(Invite).where(Invite.token == payload.token))
    if invite is None or invite.expires_at < datetime.utcnow():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invite link is invalid or has expired",
        )
    if _get_membership(db, invite.workspace_id, user.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Already a member of this workspace"
        )
    db.add(
        Membership(user_id=user.id, workspace_id=invite.workspace_id, role="member")
    )
    db.commit()
    workspace = db.get(Workspace, invite.workspace_id)
    assert workspace is not None  # guaranteed by the invite foreign key
    return _workspace_out(workspace, role="member")
