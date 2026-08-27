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
