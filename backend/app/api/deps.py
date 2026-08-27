"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def _resolve_user(raw_token: str | None, db: Session) -> User:
    if raw_token is not None:
        user_id = decode_access_token(raw_token)
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the Bearer token, else raise 401."""
    return _resolve_user(credentials.credentials if credentials else None, db)


def get_current_user_sse(
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Auth for the SSE stream only: EventSource cannot send headers, so the
    JWT may arrive as a ``?token=`` query parameter (Bearer still works)."""
    raw = credentials.credentials if credentials is not None else token
    return _resolve_user(raw, db)
