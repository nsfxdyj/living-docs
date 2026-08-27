"""Pydantic request/response schemas for the API."""

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=80)


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


class AttachmentOut(BaseModel):
    url: str
