# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Re-score every saved comparison board after a scoring change (no AI calls).

Boards store each candidate's score when built, so a scoring fix only shows on a board the
user rebuilds. This recomputes scores for every search; with --repopulate it also re-picks
each board's top 5 the way "Refresh list" does — countries the user pinned stay, countries
they removed never come back. --dry-run prints what would change and writes nothing.

Usage: python -m app.db.rescore [--repopulate] [--dry-run]
Invoked by `./xcape.sh rescore <env> [--repopulate] [--dry-run]`.
"""

from __future__ import annotations

import sys

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models.candidate import Candidate
from app.models.search import Search
from app.models.user import User
from app.services import shortlist


def _board(db, search_id: int) -> list[str]:
    rows = (
        db.query(Candidate)
        .filter(Candidate.search_id == search_id, Candidate.status == "active",
                Candidate.selected.is_(True))
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )
    return [f"{c.place.name} {round(c.match_score or 0)}" for c in rows if c.place]


def main() -> None:
    repopulate = "--repopulate" in sys.argv
    dry = "--dry-run" in sys.argv
    # The services commit as they go. For a dry run, wrap everything in one outer transaction
    # (their commits only release savepoints) and roll it back at the end.
    conn = trans = None
    if dry:
        conn = engine.connect()
        trans = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
    else:
        db = SessionLocal()
    try:
        searches = db.query(Search).order_by(Search.id).all()
        changed = 0
        for search in searches:
            user = db.get(User, search.user_id)
            if user is None or user.profile is None:
                continue
            before = _board(db, search.id)
            if repopulate:
                shortlist.repopulate_board(db, user, search)
            else:
                shortlist.rescore_candidates(db, user, search)
            db.commit()
            after = _board(db, search.id)
            if before != after:
                changed += 1
                print(f"search {search.id} ({user.email}):\n  before: {', '.join(before)}\n"
                      f"  after:  {', '.join(after)}")
        verb = "would change" if dry else "changed"
        print(f"{len(searches)} searches, {changed} boards {verb}.")
    finally:
        db.close()
        if trans is not None:
            trans.rollback()
            conn.close()


if __name__ == "__main__":
    main()
