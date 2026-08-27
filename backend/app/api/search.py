"""Full-text search routes: FTS5 (trigram) over document titles and content."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import SearchResultOut
from ..search import fts_available, search_documents
from .deps import get_current_user
from .documents import require_membership

router = APIRouter(tags=["search"])

QUERY_MAX_LENGTH = 200


@router.get(
    "/workspaces/{workspace_id}/search",
    response_model=list[SearchResultOut],
)
def search_workspace(
    workspace_id: int,
    q: str = Query(default="", max_length=QUERY_MAX_LENGTH),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchResultOut]:
    if not fts_available():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Full-text search is unavailable (SQLite FTS5 missing)",
        )
    require_membership(db, workspace_id, user.id)
    return [SearchResultOut(**hit) for hit in search_documents(db, workspace_id, q)]
