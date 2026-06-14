# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services.shortlist import _visa_value


class _User:
    def __init__(self, citizenships):
        self.citizenships = citizenships


class _Profile:
    def __init__(self, citizenships):
        self.user = _User(citizenships)


class _Place:
    def __init__(self, iso):
        self.iso_code = iso


def test_eu_citizen_moves_freely_within_eu():
    spain, attrs = _Place("ES"), {"visa": "easy"}
    assert _visa_value(attrs, _Profile(["FR"]), spain) == 1.0


def test_non_eu_resident_cannot_move_freely_within_eu():
    # A US citizen (residing in France) faces a hard move to another EU country.
    spain = _Place("ES")
    assert _visa_value({"visa": "easy"}, _Profile(["US"]), spain) == 0.3


def test_mixed_household_uses_most_restrictive_citizenship():
    # French + American household -> judged by the American passport for an EU move.
    spain = _Place("ES")
    assert _visa_value({"visa": "easy"}, _Profile(["FR", "US"]), spain) == 0.3


def test_citizen_of_destination_is_trivial():
    usa = _Place("US")
    assert _visa_value({"visa": "hard"}, _Profile(["US"]), usa) == 1.0


def test_unknown_citizenship_falls_back_to_static():
    spain = _Place("ES")
    # 'easy' on the static scale is 1.0; with no citizenship we use that accessibility.
    assert _visa_value({"visa": "easy"}, _Profile([]), spain) == 1.0
    assert _visa_value({"visa": "hard"}, _Profile(None), spain) < 1.0
