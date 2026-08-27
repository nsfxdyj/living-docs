"""Fork & merge evolution routes (M5).

Forks *take* half of the source document's vitality (capped) — the energy
is transferred, not minted — while the act of forking still charges the
source (+10): being forked means the content is valuable. Merge requests
let a fork propose its content back to a strict ancestor; accepting
replaces the target's content and transfers half of the fork's remaining
vitality, deducting it from the fork so the same vitality cannot be
merged twice.
"""

import difflib
from collections import deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..life import record_interaction, refresh_status, status_for_vitality
from ..models import Document, Interaction, MergeRequest, User
from ..notify import create_notification
from ..schemas import (
    MergeRequestCreate,
    MergeRequestOut,
    TreeNode,
    UserOut,
)
from .deps import get_current_user
from .documents import document_out, get_accessible_document, require_membership

router = APIRouter(tags=["evolution"])

# A fork takes this share of the source's vitality, capped so a fresh
# fork never starts above "stable".
FORK_VITALITY_SHARE = 0.5
FORK_VITALITY_CAP = 30.0
# One fork per user per document inside this window (anti farming).
FORK_THROTTLE_MINUTES = 30
# On accept, the target gains this share of the fork's vitality (deducted
# from the fork, so a merged fork pays out exactly once).
MERGE_VITALITY_SHARE = 0.5

MERGED_STATUS = "merged"


def _ancestor_ids(db: Session, document: Document) -> list[int]:
    """Walk the parent chain upwards; returns ancestor ids root-last."""
    ids: list[int] = []
    seen = {document.id}
    current = document
    while current.parent_id is not None:
        if current.parent_id in seen:  # defensive: never loop on bad data
            break
        seen.add(current.parent_id)
        parent = db.get(Document, current.parent_id)
        if parent is None:
            break
        ids.append(parent.id)
        current = parent
    return ids


def _merge_request_out(mr: MergeRequest) -> MergeRequestOut:
    return MergeRequestOut(
        id=mr.id,
        source_doc_id=mr.source_doc_id,
        target_doc_id=mr.target_doc_id,
        proposer_id=mr.proposer_id,
        status=mr.status,
        created_at=mr.created_at,
        decided_at=mr.decided_at,
    )


def _get_merge_request(
    db: Session, mr_id: int, user: User
) -> tuple[MergeRequest, Document, Document]:
    """Load a merge request plus both documents; 404 if anything is gone."""
    mr = db.get(MergeRequest, mr_id)
    if mr is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Merge request not found"
        )
    source = db.get(Document, mr.source_doc_id)
    target = db.get(Document, mr.target_doc_id)
    if source is None or target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="A document involved in this merge request was deleted",
        )
    require_membership(db, source.workspace_id, user.id)
    return mr, source, target


def _require_merge_decider(db: Session, target: Document, user: User) -> None:
    """Only the target document's author or the workspace owner may decide."""
    membership = require_membership(db, target.workspace_id, user.id)
    if target.author_id != user.id and membership.role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only the target author or the workspace owner can decide",
        )


def _decide_merge_request(db: Session, mr_id: int, decision: str) -> None:
    """Atomically flip an open merge request to ``decision`` (409 otherwise).

    The conditional UPDATE makes concurrent double-decides safe: only the
    first one wins the row.
    """
    result = db.execute(
        update(MergeRequest)
        .where(MergeRequest.id == mr_id, MergeRequest.status == "open")
        .values(status=decision, decided_at=datetime.utcnow())
    )
    if result.rowcount != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Merge request was already decided",
        )


def _notify_merge_decision(
    db: Session, mr: MergeRequest, target: Document, actor: User, kind: str
) -> None:
    """Tell the proposer their merge request was accepted/rejected (M6)."""
    if mr.proposer_id == actor.id:
        return
    create_notification(
        db,
        user_id=mr.proposer_id,
        workspace_id=target.workspace_id,
        kind=kind,
        payload={
            "merge_request_id": mr.id,
            "source_doc_id": mr.source_doc_id,
            "target_doc_id": target.id,
            "target_title": target.title,
            "actor_id": actor.id,
            "actor_name": actor.display_name,
        },
    )


@router.post("/documents/{document_id}/fork", status_code=status.HTTP_201_CREATED)
def fork_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = get_accessible_document(db, document_id, user)
    if source.status == MERGED_STATUS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Merged documents are archived and cannot be forked",
        )
    now = datetime.utcnow()
    window = timedelta(minutes=FORK_THROTTLE_MINUTES)
    recent_fork = db.scalar(
        select(Interaction)
        .where(
            Interaction.document_id == source.id,
            Interaction.user_id == user.id,
            Interaction.kind == "fork",
            Interaction.created_at >= now - window,
        )
        .limit(1)
    )
    if recent_fork is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You already forked this document recently",
        )
    # The fork TAKES its share from the source (energy is conserved).
    inherited = min(source.vitality * FORK_VITALITY_SHARE, FORK_VITALITY_CAP)
    source.vitality = max(0.0, source.vitality - inherited)
    fork = Document(
        workspace_id=source.workspace_id,
        parent_id=source.id,
        title=f"{source.title} (fork)",
        content_md=source.content_md,
        tags=source.tags,
        author_id=user.id,
        vitality=inherited,
    )
    fork.status = status_for_vitality(fork.vitality)
    db.add(fork)
    # Being forked is a signal of value: charge the SOURCE document.
    record_interaction(db, source, user.id, "fork")
    db.commit()
    return document_out(fork)


@router.post(
    "/documents/{document_id}/merge-requests",
    response_model=MergeRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_merge_request(
    document_id: int,
    payload: MergeRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MergeRequestOut:
    source = get_accessible_document(db, document_id, user)
    if source.parent_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only a forked document can propose a merge",
        )
    if source.status == MERGED_STATUS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This fork has already been merged",
        )
    if payload.target_doc_id == source.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Cannot merge a document into itself"
        )
    target = db.get(Document, payload.target_doc_id)
    if target is None or target.workspace_id != source.workspace_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Target document must exist in the same workspace",
        )
    # Merge direction: the target must be a strict ancestor of the fork.
    if target.id not in _ancestor_ids(db, source):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Target must be an ancestor of the fork",
        )
    duplicate = db.scalar(
        select(MergeRequest)
        .where(
            MergeRequest.source_doc_id == source.id,
            MergeRequest.status == "open",
        )
        .limit(1)
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This fork already has an open merge request",
        )
    mr = MergeRequest(
        source_doc_id=source.id, target_doc_id=target.id, proposer_id=user.id
    )
    db.add(mr)
    db.flush()  # assign mr.id for the notification payload
    if target.author_id != user.id:
        create_notification(
            db,
            user_id=target.author_id,
            workspace_id=target.workspace_id,
            kind="merge_request",
            payload={
                "merge_request_id": mr.id,
                "source_doc_id": source.id,
                "source_title": source.title,
                "target_doc_id": target.id,
                "target_title": target.title,
                "actor_id": user.id,
                "actor_name": user.display_name,
            },
        )
    db.commit()
    return _merge_request_out(mr)


@router.get(
    "/documents/{document_id}/merge-requests",
    response_model=list[MergeRequestOut],
)
def list_merge_requests(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MergeRequestOut]:
    get_accessible_document(db, document_id, user)
    stmt = (
        select(MergeRequest)
        .where(
            or_(
                MergeRequest.source_doc_id == document_id,
                MergeRequest.target_doc_id == document_id,
            )
        )
        .order_by(MergeRequest.id.desc())
    )
    return [_merge_request_out(mr) for mr in db.scalars(stmt).all()]


@router.get("/merge-requests/{mr_id}", response_model=MergeRequestOut)
def get_merge_request(
    mr_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MergeRequestOut:
    mr, _, _ = _get_merge_request(db, mr_id, user)
    return _merge_request_out(mr)


@router.get("/merge-requests/{mr_id}/diff", response_class=PlainTextResponse)
def merge_request_diff(
    mr_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    mr, source, target = _get_merge_request(db, mr_id, user)
    lines = difflib.unified_diff(
        target.content_md.splitlines(),
        source.content_md.splitlines(),
        fromfile=f"target: {target.title}",
        tofile=f"source: {source.title}",
        lineterm="",
    )
    return PlainTextResponse("\n".join(lines))


@router.post("/merge-requests/{mr_id}/accept", response_model=MergeRequestOut)
def accept_merge_request(
    mr_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MergeRequestOut:
    mr, source, target = _get_merge_request(db, mr_id, user)
    _require_merge_decider(db, target, user)
    if mr.status != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Merge request was already decided",
        )
    if source.status == MERGED_STATUS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The source fork has already been merged",
        )
    _decide_merge_request(db, mr_id, "accepted")
    # Transfer (not copy) half of the fork's vitality to the target.
    transferred = source.vitality * MERGE_VITALITY_SHARE
    source.vitality = max(0.0, source.vitality - transferred)
    target.content_md = source.content_md
    target.vitality += transferred
    target.last_interaction_at = datetime.utcnow()
    refresh_status(target)
    source.status = MERGED_STATUS
    mr.status = "accepted"
    mr.decided_at = datetime.utcnow()
    _notify_merge_decision(db, mr, target, user, "merge_accepted")
    db.commit()
    return _merge_request_out(mr)


@router.post("/merge-requests/{mr_id}/reject", response_model=MergeRequestOut)
def reject_merge_request(
    mr_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MergeRequestOut:
    mr, _, target = _get_merge_request(db, mr_id, user)
    _require_merge_decider(db, target, user)
    if mr.status != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Merge request was already decided",
        )
    _decide_merge_request(db, mr_id, "rejected")
    mr.status = "rejected"
    mr.decided_at = datetime.utcnow()
    _notify_merge_decision(db, mr, target, user, "merge_rejected")
    db.commit()
    return _merge_request_out(mr)


@router.get("/documents/{document_id}/tree", response_model=list[TreeNode])
def evolution_tree(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TreeNode]:
    """All nodes of the document's evolution tree; the client assembles it."""
    document = get_accessible_document(db, document_id, user)
    ancestors = _ancestor_ids(db, document)
    root_id = ancestors[-1] if ancestors else document.id

    # Lightweight projection: content_md is not needed for the tree.
    rows = db.execute(
        select(
            Document.id,
            Document.parent_id,
            Document.title,
            Document.author_id,
            Document.vitality,
            Document.status,
            Document.created_at,
        ).where(Document.workspace_id == document.workspace_id)
    ).all()
    children: dict[int | None, list[int]] = {}
    by_id = {row.id: row for row in rows}
    for row in rows:
        children.setdefault(row.parent_id, []).append(row.id)

    # Collect the whole tree by walking children down from the root.
    tree_ids: list[int] = []
    queue: deque[int] = deque([root_id])
    while queue:
        node_id = queue.popleft()
        if node_id not in by_id:
            continue
        tree_ids.append(node_id)
        queue.extend(children.get(node_id, []))

    nodes = [by_id[node_id] for node_id in tree_ids]
    authors = {
        author.id: author
        for author in db.scalars(
            select(User).where(User.id.in_({node.author_id for node in nodes}))
        ).all()
    }

    return [
        TreeNode(
            id=node.id,
            parent_id=node.parent_id,
            title=node.title,
            author=UserOut(
                id=node.author_id,
                email=authors[node.author_id].email,
                display_name=authors[node.author_id].display_name,
            ),
            vitality=node.vitality,
            status=node.status,
            merged=node.status == MERGED_STATUS,
            created_at=node.created_at,
        )
        for node in nodes
    ]
