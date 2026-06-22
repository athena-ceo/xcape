# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Re-tone cached criterion summaries to the neutral third-person advisor voice.

Earlier evals were written "from the newcomer's standpoint", which produced first/second-person
prose ("As a foreign resident I find…", "you will find…"). The eval prompt is now neutral third
person, but that only affects newly generated cells. This pass rewrites the EXISTING cached
summaries (summary_fr + summary_en) in place — VOICE ONLY, no re-research and no re-scoring, so
scores, levels, sources and meta are untouched (the calibration is preserved). Far cheaper than a
full regeneration.

Cache-first / idempotent / resumable: only rows whose summary still contains first/second-person
markers are rewritten, so a re-run skips the already-fixed ones. No web search.

Usage: python -m app.db.retone_evals [--limit N] [--all]
  --all : rewrite every row (not just those flagged first/second-person) — use sparingly.
Invoked by `./xcape.sh retone-evals <env> [--limit N] [--all]`.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.custom_eval import PlaceCustomEval
from app.services import ai_client
from app.core.config import settings

# A summary needs re-toning if it uses first/second person OR frames from a personal standpoint /
# perception (the artefacts of the old "from the newcomer's standpoint" prompt), rather than
# stating neutral facts. Patterns cover both English and French.
# First/second-person pronouns ("I" case-sensitive so it isn't matched inside words):
_EN_PRON = re.compile(r"\b(I'm|I've|I'll|I'd|we're|we've|we'll|my|we|our|ours|you|your|yours|you're|you'll|you've)\b", re.I)
_EN_I = re.compile(r"\bI\b")
_FR_PRON = re.compile(r"\b(je|j'|nous|notre|nos|vous|votre|vos|mon|ma|mes)\b", re.I)
# Standpoint / perception framing (high-precision: avoid neutral phrasings like "for a doctor"):
_EN_STANCE = re.compile(
    r"\bas an?\b[^.]{0,30}\b(foreign resident|newcomer|new arrival|expat|resident)\b"   # "as a foreign resident"
    r"|\bfrom (?:a |an |the )?[^.]{0,30}\b(perspective|standpoint|viewpoint|point of view)\b"  # "from a newcomer's perspective"
    r"|\b(newcomer|resident|expat)(?:'s|’s)\b[^.]{0,20}\b(perspective|standpoint|viewpoint|point of view|experience)\b",
    re.I)
_FR_STANCE = re.compile(
    r"\ben tant qu['e]\b[^.]{0,30}\b(résident|nouvel|nouvelle|arrivant|expatri)"   # "en tant que résident"
    r"|\bdu point de vue\b|\bde la perspective\b|\bpoint de vue d['e]",
    re.I)


def _needs_retone(text: str | None, fr: bool) -> bool:
    if not text:
        return False
    if fr:
        return bool(_FR_PRON.search(text) or _FR_STANCE.search(text))
    return bool(_EN_PRON.search(text) or _EN_I.search(text) or _EN_STANCE.search(text))


def _flagged(ev: PlaceCustomEval) -> bool:
    return _needs_retone(ev.summary_en, fr=False) or _needs_retone(ev.summary_fr, fr=True)


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
        },
        "required": ["summary_fr", "summary_en"],
        "additionalProperties": False,
    }


def retone_one(db, ev: PlaceCustomEval) -> bool:
    """Rewrite one row's summaries to neutral third person. Returns True if rewritten."""
    fr, en = ev.summary_fr or "", ev.summary_en or ""
    if not (fr or en):
        return False
    prompt = (
        "Rewrite these two short justifications into a neutral, friendly third-person ADVISOR "
        "voice. Keep ALL facts, figures, names and meaning EXACTLY the same and keep each to 1-2 "
        "sentences — change ONLY the voice:\n"
        "- Remove all first and second person (no \"I\", \"we\", \"my\", \"our\", \"you\", "
        "\"your\" / no \"je\", \"nous\", \"notre\", \"vous\", \"votre\").\n"
        "- Drop any personal-standpoint or perception framing (\"as a foreign resident…\", \"from "
        "a newcomer's perspective…\", \"en tant que résident…\", \"du point de vue…\"). Facts about "
        "what foreign residents can expect are fine, but state them as facts about the country "
        "(e.g. \"Foreign residents can access public healthcare after 5 years\"), not as a viewpoint "
        "or feeling.\n"
        "Do not add a score or the word \"Score\". Return summary_fr and summary_en.\n\n"
        f"summary_fr: {fr}\n\nsummary_en: {en}"
    )
    try:
        data = ai_client.respond_json(
            prompt, _schema(), schema_name="retone", web_search=False,
            model=settings.openai_chat_model, kind="custom", db=db,
        )
    except ai_client.AIUnavailable:
        return False
    new_fr = (data.get("summary_fr") or "").strip()
    new_en = (data.get("summary_en") or "").strip()
    if not (new_fr or new_en):
        return False
    if new_fr:
        ev.summary_fr = new_fr
    if new_en:
        ev.summary_en = new_en
    ev.freshness_at = datetime.now(timezone.utc)  # touched, but score/level/sources/meta unchanged
    db.commit()
    return True


def main() -> None:
    do_all = "--all" in sys.argv
    limit = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    db = SessionLocal()
    try:
        rows = db.query(PlaceCustomEval).order_by(PlaceCustomEval.id).all()
        targets = rows if do_all else [r for r in rows if _flagged(r)]
        total = len(targets)
        print(f"{total} of {len(rows)} eval rows {'(all)' if do_all else 'flagged first/second-person'}"
              f"{f' — capping at {limit}' if limit else ''}")
        done = 0
        for ev in targets:
            if limit is not None and done >= limit:
                break
            try:
                if retone_one(db, ev):
                    done += 1
                    if done % 50 == 0:
                        print(f"  re-toned {done}/{total}")
            except Exception as e:  # never let one row kill a long run
                db.rollback()
                print(f"  skip {ev.place_id}/{ev.key}: {type(e).__name__}: {e}")
        print(f"Re-toned {done} summaries.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
