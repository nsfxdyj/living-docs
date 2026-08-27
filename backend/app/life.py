"""Life engine (M4): vitality charging, decay and status transitions.

Vitality is charged by interactions (see PLAN.md section 4) and decays
periodically via ``run_decay``. The document status is derived from the
current vitality and refreshed after every charge/decay, so a withered
document revives automatically as soon as it receives new energy.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Document, Interaction

# Energy charged per interaction kind (see PLAN.md section 4).
INTERACTION_ENERGY = {"view": 1, "comment": 5, "edit": 8, "fork": 10, "vote": 2}

# Status thresholds: thriving >= 60 | stable >= 30 | fading >= 10 | withered < 10.
THRESHOLD_THRIVING = 60.0
THRESHOLD_STABLE = 30.0
THRESHOLD_FADING = 10.0


def status_for_vitality(vitality: float) -> str:
    """Map a vitality value onto the life-cycle status."""
    if vitality >= THRESHOLD_THRIVING:
        return "thriving"
    if vitality >= THRESHOLD_STABLE:
        return "stable"
    if vitality >= THRESHOLD_FADING:
        return "fading"
    return "withered"


def refresh_status(document: Document) -> str:
    """Recompute and store the document's status from its current vitality."""
    document.status = status_for_vitality(document.vitality)
    return document.status


def is_throttled_view(
    db: Session, document: Document, user_id: int, now: datetime | None = None
) -> bool:
    """True when the same user already viewed this document within the throttle window."""
    now = now or datetime.utcnow()
    window = timedelta(minutes=get_settings().view_throttle_minutes)
    recent = db.scalar(
        select(Interaction)
        .where(
            Interaction.document_id == document.id,
            Interaction.user_id == user_id,
            Interaction.kind == "view",
            Interaction.created_at >= now - window,
        )
        .limit(1)
    )
    return recent is not None


def record_interaction(
    db: Session, document: Document, user_id: int, kind: str
) -> bool:
    """Charge the document's vitality for a user interaction.

    Returns True when energy was charged. Repeat views by the same user
    inside the throttle window are ignored (no Interaction row, no energy).
    Every charge refreshes the status, reviving withered documents.
    """
    if kind == "view" and is_throttled_view(db, document, user_id):
        return False
    energy = INTERACTION_ENERGY[kind]
    db.add(
        Interaction(document_id=document.id, user_id=user_id, kind=kind, energy=energy)
    )
    document.vitality += energy
    document.last_interaction_at = datetime.utcnow()
    refresh_status(document)
    return True


def run_decay(session: Session, decay_factor: float | None = None) -> int:
    """Apply one decay tick to every document and refresh statuses.

    ``vitality *= decay_factor`` (default from settings, 0.95 ≈ 2-week
    half-life). Returns the number of documents decayed. Intended to be
    called by the scheduler job and directly from tests/scripts.
    """
    if decay_factor is None:
        decay_factor = get_settings().decay_factor
    documents = session.scalars(select(Document)).all()
    for document in documents:
        document.vitality *= decay_factor
        refresh_status(document)
    session.commit()
    return len(documents)
