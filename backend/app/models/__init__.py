"""ORM models for Living Docs (see PLAN.md section 4).

M1 note: tables only, no business logic yet. The vitality engine,
fork/merge flows and notifications arrive in later milestones.
"""

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    role: Mapped[str] = mapped_column(default="member")  # owner | member


class Invite(Base):
    """A shareable workspace invite link. The token goes into the /join/<token> URL."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    token: Mapped[str] = mapped_column(unique=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    expires_at: Mapped[datetime]


class Document(Base):
    """A living document. A non-null parent_id marks a forked variant."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    title: Mapped[str]
    content_md: Mapped[str] = mapped_column(default="")
    # JSON-encoded list of tag strings (kept as text; no FTS in the MVP).
    tags: Mapped[str] = mapped_column(default="[]")
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    vitality: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(default="thriving")  # thriving|stable|fading|withered
    last_interaction_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Interaction(Base):
    """An event that charges a document's vitality (view/edit/comment/fork/vote)."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str]  # view | edit | comment | fork | vote
    energy: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class MergeRequest(Base):
    """A request to merge a forked variant back into its source document."""

    __tablename__ = "merge_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    target_doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(default="open")  # open|accepted|rejected|orphaned
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    path: Mapped[str]
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Notification(Base):
    """An in-app notification (M6); ``payload`` is a JSON-encoded dict."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    kind: Mapped[str]  # comment | merge_request | merge_accepted | merge_rejected
    payload: Mapped[str] = mapped_column(default="{}")
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
