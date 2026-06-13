# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services.shortlist import _criterion_value


class _Profile:
    """Minimal stand-in for the ORM Profile used by the scorer."""

    def __init__(self, language_skills):
        self.language_skills = language_skills
        self.climate_pref = None
        self.user = None


def test_known_language_gives_full_value():
    spain = {"language_ease": "medium", "languages": ["Spanish"]}
    assert _criterion_value("language_ease", spain, _Profile({"known": ["Spanish"]})) == 1.0


def test_unknown_language_penalised_and_willingness_helps():
    spain = {"language_ease": "medium", "languages": ["Spanish"]}
    not_willing = _criterion_value("language_ease", spain, _Profile({"known": ["French"]}))
    willing = _criterion_value(
        "language_ease", spain, _Profile({"known": ["French"], "willing_to_learn": True})
    )
    assert not_willing < 1.0
    assert willing > not_willing


def test_one_of_several_known_languages_matches():
    # Belgium uses French/Dutch/German — a French speaker is comfortable there.
    belgium = {"language_ease": "french", "languages": ["French", "Dutch", "German"]}
    assert _criterion_value("language_ease", belgium, _Profile({"known": ["French"]})) == 1.0
