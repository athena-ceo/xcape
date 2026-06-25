# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Unified per-(country, criterion) AI evaluation cache.

Every criterion the app scores objectively — built-in (safety, taxation, healthcare…) and
user-defined (custom_*) — is rated 0-100 by the AI with a bilingual justification and
sources, cached in `place_custom_evals` and shared across all users/searches (like the
Place data). This is what lets us populate the ~190 countries that have no seed values, and
what the comparison pop-up shows instantly. Cache-first; refreshable by staleness or admin.

(The table is still named `place_custom_evals` for historical reasons; it now holds every
criterion's evaluation, not just custom ones.)
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.custom_eval import PlaceCustomEval
from app.models.place import Place
from app.services import ai_client, criteria

# 0-1 fallback values for the colour tier when an old row has no numeric score.
_LEVEL_VALUE = {"good": 1.0, "ok": 0.6, "bad": 0.3}
STALE_DAYS = 30  # evals older than this are refreshed by populate(stale_days=...)

# Bump when the evaluation PROMPT/template below changes in a way that should invalidate
# cached evals. Together with the criterion's label+description+lens it forms each row's
# prompt_fp; a mismatch marks the row stale so the next evaluate-all (or lazy refresh)
# regenerates it.
EVAL_PROMPT_VERSION = "7"  # v7: service lens (quality + access sub-scores) for healthcare/education

# Per-lens schema version — bump ONE lens to invalidate only that lens's cached rows, instead
# of churning every eval via EVAL_PROMPT_VERSION. Appended to the fingerprint only when set, so
# lenses absent here keep a byte-identical fingerprint (no needless regeneration).
# trend v2: `metric` split into bilingual `metric_fr` / `metric_en`.
LENS_VERSION = {"trend": "2"}

# Criteria judged through the ACCESS lens — for these, what matters is whether a FOREIGN
# RESIDENT can actually qualify for / reach / afford the thing (eligibility, waiting periods,
# cost to non-citizens, legal hurdles). Everything else uses the EXPERIENCE lens (quality of
# the thing as a newcomer lives it). Includes the access-oriented persona custom criteria.
ACCESS_LENS_KEYS = {
    "tax", "tax_treaty", "asset_security",
    "custom_banking_asset_protection", "custom_wealth_inheritance_tax",
    "custom_retirement_visa",
}
# SERVICE lens — services with a real quality-vs-newcomer-access split. The eval returns both
# `quality` and `access` (0-100) sub-scores; the headline score blends them, and either
# sub-score can be filtered on independently via a `key:component` filter (see shortlist).
SERVICE_LENS_KEYS = {"healthcare", "education", "custom_healthcare_for_retirees"}
SERVICE_COMPONENTS = ("quality", "access")
# TREND lens — for these the trajectory matters as much as the current level, so we capture
# structured {level, trend, window, metric} (e.g. anti-community incidents rising/falling).
TREND_LENS_KEYS = {"safety", "political_stability"}
_COMMUNITY_SAFETY_PREFIX = "custom_safety_for_my_community"  # per-community criterion slugs


def lens_for(key: str) -> str:
    """Which evaluation lens a criterion uses: 'service' (quality + access sub-scores), 'access'
    (can a newcomer get it), 'trend' (level + trajectory), or 'experience' (lived quality)."""
    if key in SERVICE_LENS_KEYS:
        return "service"
    if key in TREND_LENS_KEYS or key.startswith(_COMMUNITY_SAFETY_PREFIX):
        return "trend"
    return "access" if key in ACCESS_LENS_KEYS else "experience"


# Each eval scores ONE country in isolation (the model never sees the others), which makes models
# cluster and inflate — especially for famous countries. Force an absolute, full-range, global
# calibration so strong and lesser-known countries are genuinely differentiated.
_CALIBRATION = (
    "Calibrate on a GLOBAL absolute scale across ALL countries worldwide, using the FULL 0-100 "
    "range — do not cluster scores and do not grade on reputation or region. Anchors: ~90+ = "
    "among the very best in the world; ~70 = clearly strong; ~50 = global average / typical; "
    "~30 = clearly weak; ~10 = among the worst. A well-known country with only average provision "
    "should score around 50, and a lesser-known country that genuinely excels should score high."
)


def prompt_fingerprint(label: str, description: str | None, lens: str = "experience") -> str:
    """Short stable hash of (template version, lens, label, description) — the invariant part of
    the prompt (place name excluded). Changes whenever the prompt, lens or wording does."""
    raw = f"{EVAL_PROMPT_VERSION}\x1f{lens}\x1f{label}\x1f{description or ''}"
    lv = LENS_VERSION.get(lens)
    if lv:  # append only when set, so other lenses' fingerprints are unchanged
        raw += f"\x1f{lv}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def slugify(label: str) -> str:
    """Stable key for a custom criterion phrase so it reuses cached evaluations."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(label).strip().lower()).strip("_")
    return ("custom_" + slug)[:80] or "custom_criterion"


def level_from_score(score: int | None) -> str:
    """Colour tier from a 0-100 score, matching shortlist.quality_tier thresholds."""
    if score is None:
        return "ok"
    return "good" if score >= 70 else ("ok" if score >= 45 else "bad")


def value_of(ev: PlaceCustomEval) -> float:
    """0-1 scoring value: the numeric score when present, else the level fallback."""
    if ev.score is not None:
        return max(0.0, min(1.0, ev.score / 100))
    return _LEVEL_VALUE.get(ev.level, 0.5)


def _is_stale(ev: PlaceCustomEval, stale_days: int) -> bool:
    if not stale_days or ev.freshness_at is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    ts = ev.freshness_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < cutoff


def _fresh(ev: PlaceCustomEval, fp: str, stale_days: int) -> bool:
    """A cached eval is fresh when it isn't time-stale AND was produced by the current prompt
    (its fingerprint matches). A prompt change flips fp, marking the row for regeneration."""
    return ev.prompt_fp == fp and not _is_stale(ev, stale_days)


def _eval_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def _service_schema() -> dict:
    """Eval schema for service-lens criteria (healthcare, education): a headline score plus
    separate quality and access sub-scores, so each can be shown and filtered independently."""
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "quality": {"type": "integer", "minimum": 0, "maximum": 100},  # intrinsic quality
            "access": {"type": "integer", "minimum": 0, "maximum": 100},   # ease for a newcomer
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "quality", "access", "summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def _trend_schema() -> dict:
    """Eval schema for trend-lens criteria: adds structured level/trend/window/metric so the
    trajectory (e.g. anti-community incidents rising vs falling) is first-class data, not buried
    in prose."""
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "level": {"type": "string", "enum": ["high", "moderate", "low"]},
            "trend": {"type": "string", "enum": ["improving", "stable", "worsening"]},
            "window": {"type": "string"},   # period assessed, e.g. "2023–2025"
            "metric_fr": {"type": "string"},  # one-line factual basis, French (cite a monitor)
            "metric_en": {"type": "string"},  # one-line factual basis, English (cite a monitor)
            "summary_fr": {"type": "string"},
            "summary_en": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "level", "trend", "window", "metric_fr", "metric_en",
                     "summary_fr", "summary_en", "sources"],
        "additionalProperties": False,
    }


def evaluate(
    db: Session, place: Place, key: str, label: str, description: str | None = None,
    *, lens: str | None = None, user_id: int | None = None, force: bool = False, stale_days: int = 0,
) -> PlaceCustomEval | None:
    """Rate one place on one criterion (cache-first). Re-evaluates if `force` or the cached
    row is older than `stale_days`. Returns the (possibly cached) eval, or None if AI is off."""
    existing = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
        .first()
    )
    lens = lens or lens_for(key)
    fp = prompt_fingerprint(label, description, lens)
    if existing and not force and _fresh(existing, fp, stale_days):
        return existing

    # The short label is the column name; the (optional) description explains what to judge.
    criterion = label + (f": {description}" if description else "")
    # Origin-neutral on purpose: these evals are a SHARED cross-user cache, so they must not
    # bake in any one user's home country / citizenship. Per-user framing (relocating FROM X)
    # lives in the chatbot context instead.
    if lens == "service":
        focus = (
            "Report TWO sub-scores 0-100: quality (the intrinsic quality of the service for "
            "residents) and access (how easily a FOREIGN RESIDENT / newcomer can actually obtain "
            "it — eligibility, qualifying or waiting period, cost to non-citizens, language). The "
            "headline score (0-100) is the newcomer's overall usefulness, reflecting BOTH (a "
            "world-class service that newcomers can't readily get should NOT score top)."
        )
    elif lens == "access":
        focus = (
            "Score 0 (poor) to 100 (excellent) specifically for how well a FOREIGN RESIDENT can "
            "actually ACCESS and benefit from it: eligibility and legal/visa requirements, any "
            "qualifying or waiting period, cost to non-citizens / new arrivals, language barriers "
            "and practical hurdles — NOT just the general domestic quality for locals. Judge the "
            "OUTCOME, recognising functional equivalents: a pathway that achieves the same end "
            "under a different name still counts — do not score something weak merely because a "
            "specifically-named program is absent if a general route delivers the same result."
        )
    elif lens == "trend":
        focus = (
            "Both the current LEVEL and the recent TRAJECTORY matter. Report: level (high / "
            "moderate / low, where high = best for a resident); trend (improving / stable / "
            "worsening); window (the period assessed, e.g. \"2023–2025\"); metric_fr and "
            "metric_en (the SAME one-line factual basis, written in French and in English "
            "respectively, citing a recognised monitor where one exists — e.g. ADL or CST for "
            "Jewish communities, ILGA for LGBTQ+, OSCE-ODIHR / EU-FRA hate-crime data, or "
            "national statistics — with figures or direction if available). The score (0-100) "
            "must reflect BOTH: a high but worsening situation scores below a stable high one, "
            "and a low but improving one above a worsening low one."
        )
    else:
        focus = (
            "Score 0 (poor) to 100 (excellent) for how good this is to live with day-to-day for a "
            "FOREIGN RESIDENT who has settled there, noting any barrier a newcomer specifically "
            "faces (e.g. language or lack of local networks). Judge the lived quality, not "
            "bureaucratic eligibility."
        )
    schema = (_trend_schema() if lens == "trend"
              else _service_schema() if lens == "service" else _eval_schema())
    schema_name = ("criterion_eval_trend" if lens == "trend"
                   else "criterion_eval_service" if lens == "service" else "criterion_eval")
    try:
        data = ai_client.respond_json(
            f"Assess {place.name} for someone who has moved there as a FOREIGN RESIDENT — a "
            f"newcomer, not a native citizen — on this criterion: \"{criterion}\". {focus} "
            f"{_CALIBRATION} Add a concise, specific 1-2 sentence justification (include a "
            f"concrete fact or figure where possible) in French (summary_fr) and English "
            f"(summary_en). Write as a neutral, friendly advisor giving an overall assessment "
            f"grounded in facts. Do NOT write in the FIRST PERSON (no \"I\", \"we\", \"my\", "
            f"\"our\") — the assessment describes the country, not your own experience; overall "
            f"impressions (e.g. \"broadly safe but…\") are welcome as long as they are backed by "
            f"facts. Do NOT restate the number or write \"Score:\" in the summaries, and keep any "
            f"level you report consistent with the score. Use web search and favour the most recent "
            f"data (2025–2026). Put sources ONLY in the sources array as bare https URLs.",
            schema,
            schema_name=schema_name,
            web_search=True,
            model=settings.openai_chat_model,  # lightweight scoring → use the faster model
            kind="custom",
            db=db,
            user_id=user_id,
        )
    except ai_client.AIUnavailable:
        return None

    score = data.get("score")
    # Structured extras → stored in meta for first-class display + component filtering.
    meta = None
    if lens == "trend":
        meta = {k: data.get(k) for k in ("level", "trend", "window", "metric_fr", "metric_en")
                if data.get(k)}
    elif lens == "service":
        meta = {k: data.get(k) for k in SERVICE_COMPONENTS if data.get(k) is not None}
    if existing:  # refresh in place
        existing.score = score
        existing.level = level_from_score(score)
        existing.label = label
        existing.summary_fr = data.get("summary_fr")
        existing.summary_en = data.get("summary_en")
        existing.sources = data.get("sources", [])
        existing.meta = meta
        existing.prompt_fp = fp
        existing.freshness_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    ev = PlaceCustomEval(
        place_id=place.id, key=key, label=label, score=score,
        level=level_from_score(score),
        summary_fr=data.get("summary_fr"), summary_en=data.get("summary_en"),
        sources=data.get("sources", []), meta=meta, prompt_fp=fp,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def populate(db: Session, places: list[Place], keys: list[str], *,
             stale_days: int = 0, force: bool = False, limit: int | None = None,
             respect_buckets: bool = True) -> int:
    """Progressively evaluate (place × key) cells, cache-first. Returns how many AI calls
    were made. Resumable: re-run to continue. `limit` caps the AI calls this run.
    With `respect_buckets`, an objective leaf that already has a seed bucket value is left
    alone (no AI call) unless `force` — this bounds cost to the genuinely-missing cells."""
    defs = criteria.definitions()  # objective built-ins, resolved the same way as everywhere
    made = 0
    for place in places:
        attrs = place.attributes or {}
        for key in keys:
            if limit is not None and made >= limit:
                return made
            d = defs.get(key)
            if d is None:
                continue  # not an AI-evaluable criterion
            before = (
                db.query(PlaceCustomEval)
                .filter(PlaceCustomEval.place_id == place.id, PlaceCustomEval.key == key)
                .first()
            )
            fp = prompt_fingerprint(d["label"], d.get("description"), lens_for(key))
            if before and not force and _fresh(before, fp, stale_days):
                continue  # already current for this prompt
            # No eval yet AND only a coarse seed bucket present → leave it (bounds cost) unless
            # forced. A version-stale existing row (above) is always refreshed.
            if before is None and respect_buckets and not force and attrs.get(key):
                continue
            try:
                ev = evaluate(db, place, key, d["label"], d.get("description"),
                              force=force, stale_days=stale_days)
            except Exception as e:  # never let one cell kill a long unattended run
                db.rollback()
                print(f"  skip {place.name}/{key}: {type(e).__name__}: {e}")
                continue
            if ev is None:
                continue
            made += 1
    return made


def _rows_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, PlaceCustomEval]:
    if not keys:
        return {}
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id == place_id, PlaceCustomEval.key.in_(keys))
        .all()
    )
    return {r.key: r for r in rows}


def levels_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, str]:
    """Map of {key: level} for a place — used for the cell colour tier."""
    return {k: r.level for k, r in _rows_for_place(db, place_id, keys).items()}


def _emit_values(out: dict[str, float], r: PlaceCustomEval) -> None:
    """Add a row's 0-1 value under its key, plus any service sub-components as `key:component`
    (e.g. healthcare:access) so a filter can target one component through the normal path."""
    out[r.key] = value_of(r)
    m = r.meta or {}
    for comp in SERVICE_COMPONENTS:
        v = m.get(comp)
        if isinstance(v, (int, float)):
            out[f"{r.key}:{comp}"] = max(0.0, min(1.0, v / 100))


def values_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, float]:
    """Map of {key: 0-1 value} for a place (incl. `key:component` sub-values) — used for
    ranking and component filtering."""
    out: dict[str, float] = {}
    for r in _rows_for_place(db, place_id, keys).values():
        _emit_values(out, r)
    return out


def values_for_places(db: Session, place_ids: list[int], keys: list[str]) -> dict[int, dict[str, float]]:
    """Batch {place_id: {key: 0-1 value}} for scoring a whole pool in one query (incl. service
    `key:component` sub-values for component filters)."""
    if not place_ids or not keys:
        return {}
    rows = (
        db.query(PlaceCustomEval)
        .filter(PlaceCustomEval.place_id.in_(place_ids), PlaceCustomEval.key.in_(keys))
        .all()
    )
    out: dict[int, dict[str, float]] = {}
    for r in rows:
        _emit_values(out.setdefault(r.place_id, {}), r)
    return out


def evals_for_place(db: Session, place_id: int, keys: list[str]) -> dict[str, PlaceCustomEval]:
    """All cached eval rows for a place keyed by criterion key (one query)."""
    return _rows_for_place(db, place_id, keys)


def reason_from_eval(ev: PlaceCustomEval) -> dict:
    """Pop-up justification from an eval row. Carries BOTH languages so the frontend can
    show the right one for the current UI language without re-fetching the board."""
    return {
        "code": "custom",
        "text_fr": ev.summary_fr or ev.summary_en or "",
        "text_en": ev.summary_en or ev.summary_fr or "",
        "score": ev.score,
        "sources": ev.sources or [],
    }
