# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

from app.services.shortlist import _effective_weights


class _Profile:
    def __init__(self, household, intends=None):
        self.household_type = household
        self.intends_children = intends
        self.reasons_leaving = []
        self.criteria_weights = {}


def test_education_weighted_for_families():
    assert _effective_weights(_Profile("family")).get("education", 0) > 0


def test_education_weighted_for_couples_intending_children():
    assert _effective_weights(_Profile("couple", intends=True)).get("education", 0) > 0


def test_education_ignored_otherwise():
    assert _effective_weights(_Profile("single")).get("education", 0) == 0
    assert _effective_weights(_Profile("couple", intends=False)).get("education", 0) == 0
