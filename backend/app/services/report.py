# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Generate a PDF report for a search: a summary comparison table plus all the details
(per-criterion scores, justifications and sources, and the user's profile). Built
server-side from the database so the report is complete, even for details not on screen."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.search import Search
from app.models.user import User
from app.services import comparison, criteria, criterion_eval
from app.services import shortlist as sl

_T = {
    "title": {"fr": "xCape — Rapport de relocalisation", "en": "xCape — Relocation report"},
    "generated": {"fr": "Généré le", "en": "Generated"},
    "profile": {"fr": "Votre profil", "en": "Your profile"},
    "summary": {"fr": "Tableau comparatif", "en": "Comparison summary"},
    "details": {"fr": "Détails par pays", "en": "Country details"},
    "criterion": {"fr": "Critère", "en": "Criterion"},
    "current": {"fr": "Actuel", "en": "Current"},
    "score": {"fr": "Score", "en": "Score"},
    "sources": {"fr": "Sources", "en": "Sources"},
    "residence": {"fr": "Résidence", "en": "Residence"},
    "citizenship": {"fr": "Citoyenneté(s)", "en": "Citizenship(s)"},
    "household": {"fr": "Foyer", "en": "Household"},
    "budget": {"fr": "Budget mensuel", "en": "Monthly budget"},
    "climate": {"fr": "Climat préféré", "en": "Preferred climate"},
    "languages": {"fr": "Langues", "en": "Languages"},
    "communities": {"fr": "Communautés", "en": "Communities"},
    "reasons": {"fr": "Raisons du départ", "en": "Reasons for leaving"},
}


def _label(key: str, lang: str, custom: dict[str, str]) -> str:
    if key in custom:
        return custom[key]
    return criteria.label(key, lang)  # built-in labels come from the registry (one source)


def build_report(db: Session, user: User, search: Search) -> bytes:
    lang = (user.locale or "fr")[:2]
    tr = lambda k: _T[k][lang]  # noqa: E731

    profile = user.profile
    baseline = comparison.get_current_country_place(db, user, research=False)
    cands = (
        db.query(Candidate)
        .filter(Candidate.search_id == search.id, Candidate.status == "active",
                Candidate.selected.is_(True))
        .order_by(Candidate.match_score.desc().nullslast())
        .all()
    )
    cands = [c for c in cands if c.place]

    custom_defs = search.custom_criteria or []
    custom_labels = {c["key"]: c.get("label", c["key"]) for c in custom_defs if c.get("key")}
    eval_keys = criteria.OBJECTIVE_KEYS + list(custom_labels.keys())
    row_keys = list(sl.CRITERIA_KEYS) + list(custom_labels.keys())

    # Per-candidate cached evals (one query each) for quality + justifications.
    evals_by_cand = {c.id: criterion_eval.evals_for_place(db, c.place_id, eval_keys) for c in cands}

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]; h2 = styles["Heading2"]; body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm, title=tr("title"))
    flow: list = [Paragraph(tr("title"), h1)]
    name = " ".join(filter(None, [user.first_name, user.last_name])) or (user.email or "")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    flow.append(Paragraph(f"{name} · {tr('generated')} {when}", small))
    flow.append(Spacer(1, 0.5 * cm))

    # --- Profile ---
    flow.append(Paragraph(tr("profile"), h2))
    p = profile
    facts = [
        (tr("residence"), user.current_country or "—"),
        (tr("citizenship"), ", ".join(user.citizenships or []) or "—"),
        (tr("household"), getattr(p, "household_type", None) or "—"),
        (tr("budget"), f"{p.budget_monthly} €/mois" if (p and p.budget_monthly) else "—"),
        (tr("climate"), getattr(p, "climate_pref", None) or "—"),
        (tr("languages"), ", ".join((p.language_skills or {}).get("known", []) if p else []) or "—"),
        (tr("communities"), ", ".join(getattr(p, "minority_groups", None) or []) or "—"),
        (tr("reasons"), ", ".join(getattr(p, "reasons_leaving", None) or []) or "—"),
    ]
    for k, v in facts:
        flow.append(Paragraph(f"<b>{k}:</b> {v}", small))
    flow.append(Spacer(1, 0.5 * cm))

    # --- Summary table (criterion × country, values 0-100) ---
    flow.append(Paragraph(tr("summary"), h2))
    header = [tr("criterion")]
    if baseline:
        header.append(f"{baseline.name} ({tr('current')})")
    header += [c.place.name for c in cands]
    data = [header]

    base_attrs = (baseline.attributes or {}) if baseline else {}
    for key in row_keys:
        row = [_label(key, lang, custom_labels)]
        if baseline:
            bv = sl._criterion_value(key, base_attrs, profile, baseline)
            row.append(str(round(bv * 100)))
        for c in cands:
            evals = {k: criterion_eval.value_of(ev) for k, ev in evals_by_cand[c.id].items()}
            v = sl._criterion_value(key, c.place.attributes or {}, profile, c.place, evals)
            row.append(str(round(v * 100)))
        data.append(row)
    score_row = [tr("score")] + (["—"] if baseline else []) + [
        f"{round(c.match_score)}%" if c.match_score is not None else "—" for c in cands
    ]
    data.append(score_row)

    ncols = len(header)
    first_w = 4.5 * cm
    other_w = min(2.4 * cm, (17.0 * cm - first_w) / max(1, ncols - 1))
    table = Table(data, colWidths=[first_w] + [other_w] * (ncols - 1), repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d9488")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ccfbf1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    flow.append(table)
    flow.append(Paragraph("0–100 · " + tr("score"), small))
    flow.append(Spacer(1, 0.6 * cm))

    # --- Per-country details: score + per-criterion justifications ---
    flow.append(Paragraph(tr("details"), h2))
    for c in cands:
        score = f"{round(c.match_score)}%" if c.match_score is not None else "—"
        flow.append(Paragraph(f"{c.place.name} — {tr('score')}: {score}", styles["Heading3"]))
        rows = evals_by_cand[c.id]
        for key in row_keys:
            ev = rows.get(key)
            if ev is None:
                continue
            summary = (ev.summary_fr if lang == "fr" else ev.summary_en) or ev.summary_en or ""
            line = f"<b>{_label(key, lang, custom_labels)}</b> ({ev.score}/100): {summary}"
            flow.append(Paragraph(line, small))
            if ev.sources:
                flow.append(Paragraph(f"{tr('sources')}: " + ", ".join(ev.sources[:4]), small))
        flow.append(Spacer(1, 0.3 * cm))

    doc.build(flow)
    return buf.getvalue()
