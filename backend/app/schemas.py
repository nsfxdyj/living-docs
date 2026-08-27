"""Pydantic request/response schemas for the API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def display_name_is_mention_safe(cls, value: str) -> str:
        # display_name doubles as the @mention handle: '@' would break
        # mention parsing and control characters could smuggle markup.
        if "@" in value or any(ch.isprintable() is False for ch in value):
            raise ValueError(
                "display_name must not contain '@' or control characters"
            )
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    id: int
    name: str
    slug: str
    owner_id: int
    role: str | None = None  # the caller's own role, when relevant


class MemberOut(BaseModel):
    user_id: int
    email: str
    display_name: str
    role: str


class WorkspaceDetail(WorkspaceOut):
    members: list[MemberOut]


class InviteOut(BaseModel):
    token: str
    url: str
    expires_at: datetime


class JoinRequest(BaseModel):
    token: str


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = ""
    tags: list[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = None
    tags: list[str] | None = None


class DocumentOut(BaseModel):
    id: int
    workspace_id: int
    parent_id: int | None
    title: str
    content_md: str
    tags: list[str]
    author_id: int
    vitality: float
    status: str
    last_interaction_at: datetime
    created_at: datetime


class SearchResultOut(BaseModel):
    """One full-text search hit.

    ``snippet`` uses \\x00/\\x01 as highlight markers (never literal ``<b>``,
    so document text cannot forge highlights); clients escape HTML and map
    the markers to ``<b>``/``</b>`` tags. Empty in LIKE-fallback mode.
    """

    id: int
    title: str
    snippet: str
    vitality: float
    status: str
    rank: float


class AttachmentOut(BaseModel):
    url: str


class GardenEntry(BaseModel):
    """One plant in the workspace garden (a trunk document)."""

    id: int
    title: str
    vitality: float
    status: str
    tags: list[str]
    last_interaction_at: datetime
    author: UserOut


class MergeRequestCreate(BaseModel):
    target_doc_id: int


class MergeRequestOut(BaseModel):
    id: int
    source_doc_id: int
    target_doc_id: int
    proposer_id: int
    status: str
    created_at: datetime
    decided_at: datetime | None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    document_id: int
    author: UserOut
    body: str
    created_at: datetime


class NotificationOut(BaseModel):
    id: int
    workspace_id: int
    kind: str
    payload: dict
    read: bool
    created_at: datetime


class TreeNode(BaseModel):
    """One node of a document's evolution tree (M5)."""

    id: int
    parent_id: int | None
    title: str
    author: UserOut
    vitality: float
    status: str
    merged: bool
    created_at: datetime
