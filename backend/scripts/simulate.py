"""Simulate 30 days of garden life to tune the life-engine parameters (M4).

Creates an in-memory workspace with documents that follow different
activity profiles (hot / steady / neglected / revived), applies one
``run_decay`` tick per simulated day, and prints a vitality curve summary.

Run from the backend directory:

    python scripts/simulate.py [--days 30] [--decay 0.95] [--seed 7]
"""

import argparse
import os
import sys

# Allow running as `python scripts/simulate.py` from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Hermetic in-memory database; must be set before app modules are imported.
os.environ.setdefault("LIVING_DOCS_DATABASE_URL", "sqlite:///:memory:")

import random  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.life import INTERACTION_ENERGY, run_decay, status_for_vitality  # noqa: E402
from app.models import Document, Interaction, Membership, User, Workspace  # noqa: E402

DAYS = 30

# Each profile maps a document to its daily interaction probabilities.
PROFILES = {
    "Hot Guide": {"edit": 0.6, "view": 0.9, "views_per_day": 6},
    "Steady Runbook": {"edit": 0.15, "view": 0.7, "views_per_day": 3},
    "Neglected Draft": {"edit": 0.0, "view": 0.1, "views_per_day": 1},
    "Revived Spec": {"edit": 0.0, "view": 0.1, "views_per_day": 1},
}


def charge(session, document: Document, user_id: int, kind: str, count: int = 1) -> None:
    for _ in range(count):
        session.add(
            Interaction(
                document_id=document.id,
                user_id=user_id,
                kind=kind,
                energy=INTERACTION_ENERGY[kind],
            )
        )
        document.vitality += INTERACTION_ENERGY[kind]
    document.status = status_for_vitality(document.vitality)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DAYS)
    parser.add_argument("--decay", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    user = User(
        email="sim@example.com", password_hash="x", display_name="Sim Gardener"
    )
    session.add(user)
    session.flush()
    workspace = Workspace(name="Sim Garden", slug="sim-garden", owner_id=user.id)
    session.add(workspace)
    session.flush()
    session.add(Membership(user_id=user.id, workspace_id=workspace.id, role="owner"))

    documents = []
    for title in PROFILES:
        doc = Document(
            workspace_id=workspace.id,
            title=title,
            author_id=user.id,
            vitality=20.0,  # newly planted docs start with a small spark
            status=status_for_vitality(20.0),
        )
        session.add(doc)
        documents.append(doc)
    session.commit()

    history: dict[str, list[tuple[float, str]]] = {
        doc.title: [(doc.vitality, doc.status)] for doc in documents
    }

    for day in range(1, args.days + 1):
        for doc in documents:
            profile = PROFILES[doc.title]
            # The revived spec gets a burst of attention halfway through.
            if doc.title == "Revived Spec" and day == args.days // 2:
                charge(session, doc, user.id, "edit", count=6)
            if rng.random() < profile["edit"]:
                charge(session, doc, user.id, "edit")
            if rng.random() < profile["view"]:
                charge(session, doc, user.id, "view", count=profile["views_per_day"])
        run_decay(session, decay_factor=args.decay)
        session.commit()
        for doc in documents:
            session.refresh(doc)
            history[doc.title].append((doc.vitality, doc.status))

    checkpoints = sorted({0, 7, 14, 21, args.days})
    print(f"Simulation: {args.days} days, decay factor {args.decay}, seed {args.seed}")
    header = f"{'document':<18}" + "".join(f"day {d:>3}       " for d in checkpoints)
    print(header)
    print("-" * len(header))
    for doc in documents:
        curve = history[doc.title]
        cells = []
        for day in checkpoints:
            vitality, status = curve[day]
            cells.append(f"{vitality:6.1f} {status[:4]}")
        print(f"{doc.title:<18}" + "  ".join(f"{c:<12}" for c in cells))
    print()
    for doc in documents:
        curve = history[doc.title]
        final_vitality, final_status = curve[-1]
        transitions = [
            f"day {i} -> {status}"
            for i, (_, status) in enumerate(curve)
            if i > 0 and status != curve[i - 1][1]
        ]
        print(
            f"{doc.title}: final vitality {final_vitality:.1f} ({final_status}); "
            + ("; ".join(transitions) if transitions else "no status change")
        )


if __name__ == "__main__":
    main()
