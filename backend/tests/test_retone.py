# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.db.retone_evals import _needs_retone


def test_flags_first_and_second_person():
    assert _needs_retone("As a foreign resident I find France livable.", fr=False)
    assert _needs_retone("You will find a small expat community.", fr=False)
    assert _needs_retone("From a newcomer's perspective it is safe.", fr=False)
    assert _needs_retone("En tant que résident étranger, je trouve le pays sûr.", fr=True)
    assert _needs_retone("Du point de vue d'un nouvel arrivant, c'est cher.", fr=True)


def test_neutral_factual_text_is_not_flagged():
    # Plain third-person facts — must NOT be flagged (else the pass never converges).
    assert not _needs_retone(
        "Portugal remains broadly safe, with low homicide and overall crime levels.", fr=False)
    assert not _needs_retone(
        "Foreign residents can access public healthcare after registering for a Número de Utente.",
        fr=False)
    # Neutral French phrasings that earlier over-matched ("pour un médecin", "pour un arrivant").
    assert not _needs_retone(
        "Les consultations coûtent environ 60–80 € pour un médecin généraliste.", fr=True)
    assert not _needs_retone(
        "Les barrières pour un nouvel arrivant incluent la langue.", fr=True)
